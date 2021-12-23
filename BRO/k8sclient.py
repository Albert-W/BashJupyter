#!/usr/bin/env python3

"""
This module is used to create a kubernetes client.
"""

import time
import re
import inspect
import os
import random
from typing import List
from kubernetes import client
from kubernetes import config
from kubernetes.config import ConfigException
from kubernetes.stream import stream
from kubernetes.client.rest import ApiException
from kubernetes.client.models.v1_pod import V1Pod

import utilprocs


class KubernetesClient:
    """
    This class consists of various methods needed
    to create a Kubernetes client.
    """

    def __init__(self):
        """
        This is the constructor of the class.

        :param self: self is an instance of the class\
        and also binds the attributes with the given arguments.
        :param test_pod_prefix: fixed part of the test pod name
        """
        try:
            # config from inside k8s cluster
            config.load_incluster_config()
        except ConfigException:
            # config from outside k8s cluster
            config.load_kube_config()
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.rbac_v1 = client.RbacAuthorizationV1Api()
        self.custom_api = client.CustomObjectsApi()
        # gets the env variables for test file / directory
        self.script_name = os.environ.get('nose_test')
        self.script_path = os.environ.get('test_cases_dir')
        # gets the test pod prefix
        self._test_pod_prefix = utilprocs.generate_test_pod_prefix(
            str(self.script_path), str(self.script_name))

    @staticmethod
    def _write_log(logname: str, log: str) -> bool:
        """
        Write k8s pod log to file

        Args:
            logname: destination log file name
            log: pod log as returned from read_namespaced_pod_log

        Returns:
            True if successful, False otherwise
        """
        try:
            with open(logname, 'w+') as f_log:
                f_log.write('{}\n'.format(log))
        except Exception as e_obj:
            utilprocs.log(
                'Error writing file {}: {}'.format(logname, e_obj)
            )
            return False

        return True

    def _retrieve_pod_logs(
            self, pod: V1Pod, scenario: str, namespace: str, logpath: str
    ):
        """
        Retrieve logs from a pod

        Args:
            pod: pod object as returned from self.core_v1.list_namespaced_pod
            scenario: string that you want to add to log
                file names. It could be:
                - <string>: a string that is meaningful to you
                - 'caller': the name of the caller function will be
                    appended to the file names
            namespace: namespace name
            logpath: path where to save the logs

        Returns:
            True if successful, False otherwise

        """
        for container in pod.spec.containers:
            if scenario != '':
                logname = '{}{}_{}_{}.log'.format(
                    logpath, pod.metadata.name, container.name, scenario
                )
            else:
                logname = '{}{}_{}.log'.format(
                    logpath, pod.metadata.name, container.name
                )

            try:
                log = self.core_v1.read_namespaced_pod_log(
                    name=pod.metadata.name, namespace=namespace,
                    container=container.name
                )
            except Exception as e_obj:
                utilprocs.log(
                    'Error while retrieving logs from '
                    'container {} in pod {} in namespace {}: {}'.
                    format(container.name, pod.metadata.name,
                           namespace, e_obj)
                )
                continue

            if not self._write_log(logname, log):
                return False

        return True

    def get_pod_logs(
            self, namespace: str, name: str = 'all',
            scenario: str = ''
    ) -> bool:
        """
        Retrieve k8s logs for the pod in the namespace

        Args:
            namespace: namespace name
            name: name of the pod you want the log for. 'all' will retrieve
                logs from all the pods in the namespace. Default to 'all'
            scenario: string that you want to add to log
                file names. It could be:
                - <string>: a string that is meaningful to you
                - 'caller': the name of the caller function will be
                    appended to the file names

        Returns:
            True if succeed, False otherwise
        """
        logpath = "/var/log/"

        if scenario == 'caller':
            try:
                # get the name of the caller function
                scenario = inspect.stack()[1][3]
            except Exception as e_obj:
                utilprocs.log(
                    'Error while retrieving caller function name: {}'.format(
                        e_obj
                    )
                )
                return False

        pods = []
        if name != 'all':
            podlist = self.list_pods_from_namespace(namespace, name)

            if len(podlist.items) > 1:
                utilprocs.log(
                    'Too many result for pod name {}'.format(name)
                )
                return False

            if not podlist.items:
                utilprocs.log(
                    'No pod found with name {}'.format(name)
                )
                return False

            for pod in podlist.items:
                pods.append(pod)
        else:
            podlist = self.list_pods_from_namespace(namespace)
            for pod in podlist.items:
                podname = pod.metadata.name
                if podname.startswith(self._test_pod_prefix):
                    continue
                pods.append(pod)

        for pod in pods:
            if not self._retrieve_pod_logs(pod, scenario, namespace, logpath):
                return False

        return True

    def list_pods_from_namespace(self, namespace, name=None):
        """
        Retrieves list of pods from the namespace

        Args:
            namespace: namespace name
            name: name of the pod.

        Returns:
            List of pods found

        Raises:
            ApiException if any error during api call
        """
        if name is None:
            field_selector = ""
        else:
            field_selector = 'metadata.name={}'.format(name)

        podlist = []
        exception_count = 3
        while True:
            try:
                podlist = self.core_v1.list_namespaced_pod(
                    namespace,
                    field_selector=field_selector
                )
                break
            except Exception as e_obj:
                utilprocs.log(
                    (
                        "Exception when trying to find pods"
                        "in namespace:{} Error: {}".format(namespace, e_obj)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise ApiException
                continue

        return podlist

    def list_statefulset_from_namespace(self, namespace, name=None) -> list:
        """
        Retrieves list of statefulset from the namespace. If a specific
        statefulset name is specified, the method will retrieve only
        that statefulset from the namespace

        Args:
            namespace: namespace name
            name: name of the statefulset

        Returns:
            List of statefulset found

        Raises:
            ApiException if any error during api call
        """
        if name is None:
            field_selector = ""
        else:
            field_selector = 'metadata.name={}'.format(name)

        statefulset_list = []
        exception_count = 3
        while True:
            try:
                statefulset_list = self.apps_v1.list_namespaced_stateful_set(
                    namespace,
                    field_selector=field_selector
                )
                break
            except Exception as e_obj:
                utilprocs.log(
                    (
                        "Exception when trying to find statefulsets"
                        "in namespace:{} Error: {}".format(namespace, e_obj)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise ApiException
                continue

        return statefulset_list.items

    def get_namespace_secrets(
            self, namespace: str,
            secret_names: List[str] = None
    ) -> List[client.V1Secret]:
        """
        Retrieve secrets from a namespace

        Args:
            namespace: namespace name
            secret_names: list of all the secrets to retrieve.
                defaults to None

        Returns:
            list of secrets found

        Raises:
            ApiException if any error during api call
        """
        exception_count = 3
        while True:
            try:
                api_response = self.core_v1.list_namespaced_secret(namespace)
            except ApiException as e_obj:
                utilprocs.log(
                    ("Exception when calling CoreV1Api->"
                     "list_namespaced_secret: {}").format(e_obj))
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            secrets = []
            for secret in api_response.items:
                if (secret_names is not None and
                        secret.metadata.name in secret_names):
                    secrets.append(secret)

            return secrets

    def create_namespace_secret(
            self, name: str, namespace: str,
            secret_type: str, data: dict
    ) -> client.V1Secret:
        """
        Create a secret in a namespace

        Args:
            name: secret name
            namespace: namespace name
            secret_type: secret type
            data: data to save in the secret

        Returns:
            client.V1Secret object

        Raises:
            ApiException if something wrong with secret creation

        Examples:
            create_namespace_secret(
                namespace='namespace-name',
                name='rbd-client-secret',
                secret_type='kubernetes.io/rbd',
                data={'key': 'base64-encrypted-string'}
            )
        """
        body = client.V1Secret(
            type=secret_type,
            metadata=client.V1ObjectMeta(namespace=namespace, name=name),
            data=data,
        )
        exception_count = 3
        while True:
            try:
                api_response = self.core_v1.create_namespaced_secret(
                    namespace, body)
            except ApiException as e_obj:
                utilprocs.log(
                    (
                        "Exception when calling CoreV1Api->"
                        "create_namespaced_secret: {}"
                    ).format(e_obj)
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            return api_response

    def create_custom_resource(
            self, namespace: str, group: str,
            version: str, plural: str, body: str):
        """
        Create a custom resource in a namespace

        Args:
            namespace: namespace name
            group: custom resource group name
            version: custom resource version
            plural: plural form of resource name
            body: content of yaml text used in creating resource
        """
        self.custom_api.create_namespaced_custom_object(
            group=group,
            version=version,
            namespace=namespace,
            plural=plural,
            body=body,
        )

    def create_namespace(self, namespace: str) -> client.V1Namespace:
        """
        Create a new namespace. It could be use to run the test
        pod and the relevant micro-services

        Args:
            namespace: name of the namespace to create

        Returns:
            client.V1Namespace object

        Raises:
            ApiException if something wrong with namespace creation
        """
        body = client.V1Namespace()
        body.metadata = client.V1ObjectMeta(name=namespace)
        exception_count = 3
        while True:
            try:
                api_response = self.core_v1.create_namespace(body)
            except ApiException as e_obj:
                utilprocs.log(
                    (
                        "Exception when calling CoreV1Api->create_namespace"
                        ": {}"
                    ).format(e_obj)
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            return api_response

    def create_namespace_rolebinding(
            self,
            namespace: str,
            metadata: client.V1ObjectMeta,
            role_ref: client.V1RoleRef,
            subjects: List[client.V1Subject]
    ):
        """
        Create a role binding in a namespace

        Args:
            namespace: namespace name
            metadata: metadata for role binding
            role_ref: Role reference for the binding
            subjects: list of subjects for the binding

        Returns:
            V1ClusterRoleBinding object

        Raises:
            ApiException if something wrong with binding creation

        Examples:
            create_rolebinding(
                metadata = client.V1ObjectMeta(
                    name="role-bind-name",
                    namespace='namespace-name'
                ),
                role_ref = client.V1RoleRef(
                    api_group='rbac.authorization.k8s.io',
                    kind='ClusterRole',
                    name='cluster-admin'
                ),
                subjects = [
                    client.V1Subject(
                        kind='ServiceAccount',
                        name='default',
                        namespace='namespace-name'
                    )
                ]

        """
        body = client.V1ClusterRoleBinding(
            metadata=metadata,
            role_ref=role_ref,
            subjects=subjects
        )
        exception_count = 3
        while True:
            try:
                api_response = self.rbac_v1. \
                    create_namespaced_role_binding(namespace, body)
            except ApiException as e_obj:
                utilprocs.log(
                    (
                        "Exception when calling RbacAuthorizationV1Api->"
                        "create_cluster_role_binding: {}".format(e_obj)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            return api_response

    def create_namespace_statefulset(self, namespace: str,
                                     metadata: client.V1ObjectMeta,
                                     spec: client.V1StatefulSetSpec
                                     ) -> client.V1Status:
        """
       Create a statefulset in a namespace

        Args:
            :param namespace: namespace name
            :param metadata: metadata for statefulset
            :param spec: desired identities of pods

        Returns:
            V1Status object

        Raises:
            ApiException if something wrong with statefulset creation

        Examples:
            create_statefulset(
                namespace='namespace-name',
                metadata = client.V1ObjectMeta(
                    name="statefulset-name",
                ),
                spec = client.V1StatefulSetSpec(
                    service_name='statefulset-name',
                    replicas=1,
                    client.V1PodTemplateSpec(
                    ..
                    )
                )
            )
        """
        body = client.V1StatefulSet(
            metadata=metadata,
            spec=spec
        )
        exception_count = 3
        while True:
            try:
                api_response = self.apps_v1. \
                    create_namespaced_stateful_set(namespace, body)
            except ApiException as e_obj:
                utilprocs.log(
                    (
                        "Exception when calling " +
                        "create_namespaced_stateful_set->"
                        "create_namespaced_stateful_set: {} - {}".
                        format(e_obj, e_obj.reason)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            return api_response

    @staticmethod
    def delete_namespace_rolebinding(
            name: str, namespace: str,
    ) -> client.V1Status:
        """
        Delete a role binding in a namespace

        Args:
            name: role binding name
            namespace: namespace name

        Returns:
            V1Status object

        Raises:
            ApiException if something wrong with binding deletion

        """
        body = client.V1DeleteOptions()
        exception_count = 3
        while True:
            try:
                api_response = client. \
                    RbacAuthorizationV1Api(). \
                    delete_namespaced_role_binding(name, namespace, body)
            except ApiException as e_obj:
                utilprocs.log(
                    (
                        "Exception when calling RbacAuthorizationV1Api->"
                        "delete_namespaced_role_binding: {}".format(e_obj)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            return api_response

    @staticmethod
    def delete_namespace_statefulset(
            name: str, namespace: str,
    ) -> client.V1Status:
        """
        Delete a statefulset in a namespace

        Args:
            name: statefulset name
            namespace: namespace name

        Returns:
            V1Status object

        Raises:
            ApiException if something wrong with statefulset deletion

        """
        body = client.V1DeleteOptions()
        exception_count = 3
        while True:
            try:
                api_response = client.AppsV1Api(). \
                    delete_namespaced_stateful_set(
                        name=name,
                        namespace=namespace,
                        body=body)
            except ApiException as e_obj:
                utilprocs.log(
                    (
                        "Exception when calling AppsV1Api->"
                        "delete_namespaced_stateful_set: {} - {}".
                        format(e_obj, e_obj.reason)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            return api_response

    def delete_namespace(
            self, namespace: str,
    ) -> client.V1Status:
        """
        Delete a namespace

        Args:
            namespace: namespace name

        Returns:
            V1Status object

        Raises:
            ApiException if something wrong with binding creation

        """
        body = client.V1DeleteOptions()
        exception_count = 3
        while True:
            try:
                api_response = self.core_v1.delete_namespace(
                    namespace, body=body, grace_period_seconds=0
                )
            except ApiException as e_obj:
                utilprocs.log(
                    (
                        "Exception when calling CoreV1Api->"
                        "delete_namespace: {}".format(e_obj)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            return api_response

    def delete_namespace_secret(
            self, namespace: str, name: str
    ) -> client.V1Status:
        """
        Delete a secret from a namespace

        Args:
            namespace: namespace name
            name: secret name

        Returns:
            V1Status object

        Raises:
            ApiException if something wrong with secret deletion

        """
        body = client.V1DeleteOptions()
        exception_count = 3
        while True:
            try:
                api_response = self.core_v1.delete_namespaced_secret(
                    name, namespace, body=body, grace_period_seconds=0
                )
            except ApiException as e_obj:
                try:
                    utilprocs.log(
                        (
                            "Exception when calling CoreV1Api->"
                            "delete_namespaced_secret: {}".format(e_obj)
                        )
                    )
                except Exception:
                    # The above statement could fail if this method is used
                    # from bootstrap.py, because it runs outside the test pod
                    # and /var/log (default directory for utilprocs.log) is not
                    # writable
                    print(
                        (
                            "Exception when calling CoreV1Api->"
                            "delete_namespaced_secret: {}".format(e_obj)
                        )
                    )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            return api_response

    def find_namespace(self, namespace):
        """
        Finds the namespace of the particular environment
        cluster in the pod.

        :param namespace: namespace.
        :return: A dict containing the output and the exit code\
        of the command run on the test pod
        """

        exception_count = 3
        while True:
            try:
                v1_namespace_list = self.core_v1.list_namespace()
            except ApiException as e_obj:
                utilprocs.log(
                    (
                        "Exception when trying to find "
                        "namespace: {}".format(e_obj)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            i = []
            for i in v1_namespace_list.items:
                if i.metadata.name == namespace:
                    break
            return i

    def wait_for_all_resources(self, namespace):
        """
        Waits for all resources e.g. pods, replicas etc until they are ready.

        :param self: self is an instance of the class.
        :param namespace: The namespace that the test pod is in.
        """
        self.wait_for_all_pods_to_start(namespace)
        self.wait_for_all_replica_set(namespace)
        self.wait_for_all_deployments(namespace)

    def wait_for_all_pods_to_start(self, namespace):
        """
        Waits until all the pods in the cluster are ready.

        :param self: self is an instance of the class.
        :param namespace: namespace.
        """

        def format_containers(i):
            """
            Formats the container names & lists them out in a readable format.

            :param i: the particular value of iteration in the loop.
            """

            return '\n'.join(['\n        Containername: {}'
                              '\n                Ready: {}'
                              '\n              Waiting: {}'.format
                              (c.name,
                               c.ready,
                               str(c.state.waiting).replace('\n', ''))
                              for c in i.status.container_statuses])

        utilprocs.log('Pods:')
        counter = 60
        while True:
            api_response = self.list_pods_from_namespace(namespace)
            if all(i.status.container_statuses for i in api_response.items):
                utilprocs.log('\n'.join(['\nPodname: {}'
                                         '\n    Phase: {}'
                                         '\n    Containers: {}'.format
                                         (i.metadata.name, i.status.phase,
                                          format_containers(i))
                                         for i in api_response.items]))

                if all([i.status.phase == 'Running' and
                        all([cs.ready for cs in i.status.container_statuses])
                        for i in api_response.items]):
                    return
            if counter > 0:
                counter = counter - 1
                time.sleep(10)
            else:
                raise ValueError('Timeout waiting for pods to reach '
                                 'Ready & Running')

    def wait_for_all_pods_to_terminate(self, namespace,
                                       exclude_pods_list=None,
                                       counter=60):
        """
        Waits until all pods in the namespace have
        been terminated before returning. Pods which
        should be excluded from the termination check
        are listed in exclude_pod_list.To exclude
        the framework test pod, self._test_pod_prefix should
        be added to exclude_pods_list.

        :param namespace: namespace.
        :param exclude_pods_list: pod names to be excluded
        :param counter: counter for timer with interval of 10's
        """

        all_pod_names = []

        if exclude_pods_list is None:
            exclude_pods_list = []

        if self._test_pod_prefix in exclude_pods_list:
            api_response = self.list_pods_from_namespace(namespace)
            items = api_response.items
            # all pod names list
            all_pod_names += (item.metadata.name for item in items)
            # regex for matching only the test-pod
            regex = re.compile('^{}*'.format(self._test_pod_prefix))
            # list with only the test_pod
            test_pod = list(filter(regex.match, all_pod_names))
            # remove the test pod string from the exclude pod list
            exclude_pods_list.remove(self._test_pod_prefix)
            # Add the full test pod to the exclude pod list
            exclude_pods_list.extend(test_pod)

        while True:
            api_response = self.list_pods_from_namespace(namespace)
            items = api_response.items
            pod_to_be_checked = []
            # list containing only those pod/pods to be checked
            pod_to_be_checked += (item.metadata.name for item in items
                                  if item.metadata.name
                                  not in exclude_pods_list)

            if not pod_to_be_checked:
                break

            # will check only those pods not in the excluded list
            utilprocs.log('\n'.join(
                ['\nPhase: {} Podname: {}'.format(item.status.phase,
                                                  item.metadata.name)
                 for item in items
                 if item.metadata.name in pod_to_be_checked]))

            if counter > 0:
                counter = counter - 1
                time.sleep(10)
            else:
                raise ValueError(
                    'Timeout waiting for pods to terminate')

    def wait_for_all_deployments(self, namespace):
        """
        Waits until all the deployments are ready.

        :param self: self is an instance of the class.
        :param namespace: namespace.
        """
        exception_count = 3
        while True:
            try:
                api_response = \
                    self.apps_v1.list_namespaced_deployment(namespace)
            except Exception as e_obj:
                utilprocs.log(
                    (
                        "Exception when trying to find "
                        "deployment in namespace: {}".format(e_obj)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            utilprocs.log('Deployments:')
            utilprocs.log([(i.metadata.name,
                            'Replicas ready/desired: ({}/{})'.format
                            (str(i.status.ready_replicas), i.spec.replicas))
                           for i in api_response.items])
            return

    def wait_for_all_replica_set(self, namespace):
        """
        Waits until the Replica sets are ready.

        :param self: self is an instance of the class.
        :param namespace: namespace.
        """
        exception_count = 3
        while True:
            try:
                api_response = \
                    self.apps_v1.list_namespaced_replica_set(namespace)
            except Exception as e_obj:
                utilprocs.log(
                    (
                        "Exception when trying to find "
                        "replica set in namespace: {}".format(e_obj)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            utilprocs.log('Replica sets:')
            utilprocs.log([(i.metadata.name,
                            'Replicas ready/desired: ({}/{})'.format
                            (str(i.status.ready_replicas), i.spec.replicas))
                           for i in api_response.items])
            return

    def get_statefulset_pods(self, name, namespace):
        """
        Lists all the pods in a stateful set.

        :param self: self is an instance of the class.
        :param name: name of the stateful set.
        :param namespace: namespace.
        """
        pods_list = []
        api_response = self.list_pods_from_namespace(namespace)
        items = api_response.items

        for item in items:
            # this condition checks if the pod name ends with -NN (number)
            if name in item.metadata.name and \
                    re.search(r"-\d+$", item.metadata.name) is not None:
                pods_list.append(item.metadata.name)

        return pods_list

    def delete_pod(
            self, name, namespace, counter=60, wait_for_terminating=True):
        """
        Deletes the pod and by default waits for the pod to reach
        terminating state.

        :param self: self is an instance of the class.
        :param name: name of the pod to be deleted.
        :param namespace: namespace.
        :param counter: counter for timer with interval of 10's.
        :param wait_for_terminating: if true (default) waits for pod to reach
            terminating state, if False only runs the API call
        """
        utilprocs.log('Deleting pod: {}'.format(name))
        exception_count = 3
        while True:
            try:
                self.core_v1.delete_namespaced_pod(name, namespace,
                                                   grace_period_seconds=0,
                                                   body=client.
                                                   V1DeleteOptions())
            except ApiException as e_obj:
                utilprocs.log(
                    (
                        "Exception when trying to delete "
                        "pod in namespace: {}".format(e_obj)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            if wait_for_terminating:
                self.wait_for_pod_status(name, namespace,
                                         counter, ready=False, interval=2)
            return

    def delete_random_pod_in_statefulset(self, name, namespace):
        """
        :param namespace: The namespace that the statefulset is in.
        :param name: name of the statefulset we are checking.
        """
        pods = self.get_statefulset_pods(name, namespace)
        pod = pods[random.randint(0, len(pods) - 1)]

        self.delete_pod(pod, namespace)
        self.wait_for_pod_to_start(pod, namespace)

    def wait_for_statefulset(
            self, namespace, counter=60, name: str = None
    ) -> bool:
        """Waits until all replicas are ready
        Args:
            namespace: The namespace that the pod is in.
            counter: Is the number of intervals with a
            10 seconds sleep after each interval.
            name: name of the statefulset we are checking.

        Returns;
            True if all pods in statefulset have reached the ready status

        Raises:
            RuntimeError if waiting timeout reached
        """
        utilprocs.log('Waiting for StatefulSet {}'.format(name))
        exception_count = 3
        while True:
            try:
                statefulset_list = self.list_statefulset_from_namespace(
                    namespace=namespace, name=name
                )
            except Exception as e_obj:
                utilprocs.log(
                    (
                        "Exception when trying to find "
                        "statefulset in namespace: {}".format(e_obj)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            # after retrieved the list of statefulset in the namespace
            # loop through it to check if the number of replicas configured
            # is equal to the number of replicas already deployed: if they're
            # equal remove the statefulset from the list. When the list is
            # empty, the loop exits
            for idx, statefulset in enumerate(statefulset_list):
                ready_replicas = statefulset.status.ready_replicas
                total_replicas = statefulset.status.replicas
                updated_replicas = statefulset.status.updated_replicas
                if ready_replicas == total_replicas and \
                        updated_replicas == total_replicas:
                    utilprocs.log('StatefulSet ready: {}'.format(
                        statefulset.metadata.name
                    ))
                    del statefulset_list[idx]

            if not statefulset_list:
                utilprocs.log('All StatefulSet reached ready status')
                break

            utilprocs.log(
                '{} StatefulSets need to reach the ready status'.format(
                    len(statefulset_list)
                )
            )

            counter -= 1
            if counter <= 0:
                raise RuntimeError(
                    'Timeout waiting for StatefulSet to reach ready status'
                )

            time.sleep(10)

        return True

    def wait_for_pod_to_start(self, name, namespace, counter=60):
        """
        Waits till all the containers of the pod are ready.

        :param self: self is an instance of the class.
        :param name: name of the pod we are checking.
        :param namespace: The namespace that the pod is in.
        :param counter: counter for timer with interval of 10's
        """
        return self.wait_for_pod_status(name, namespace, counter, ready=True)

    def wait_for_pod_status(self, name, namespace, counter=60, ready=True,
                            interval=10):
        """
        Waits till all the containers of the pod are ready,
        or all are not ready.

        :param self: self is an instance of the class.
        :param name: name of the pod we are checking.
        :param namespace: The namespace that the pod is in.
        :param counter: counter for timer with interval of [interval]'s
        :param ready: if True (default) wait for container ready,
             otherwise wait for container to fail readiness probe
        :param interval: interval to wait between checks in seconds, default 10
        """

        utilprocs.log('Waiting for Pod: {}'.format(name))
        exception_count = 5
        while True:
            try:
                api_response = \
                    self.core_v1.read_namespaced_pod(name, namespace)
            except Exception as e_obj:
                utilprocs.log(
                    (
                        "Exception when trying to find "
                        "pod in namespace: {}".format(e_obj)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                time.sleep(1)
                continue

            if ready:
                if api_response.status.phase == 'Running' \
                        and all(container_status.ready for
                                container_status in
                                api_response.status.container_statuses):
                    utilprocs.log('Pod ready: {}'.format(name))
                    return
            else:
                if api_response.status.phase == 'Running' \
                         and all(not container_status.ready for
                                 container_status in
                                 api_response.status.container_statuses):
                    utilprocs.log('Pod not ready: {}'.format(name))
                    return

            if counter > 0:
                counter = counter - 1
                time.sleep(interval)
            else:
                raise ValueError('Timeout waiting for pod to reach '
                                 'Ready & Running')

    def get_namespace_pod_details(self, namespace):
        """
        Listing all pod details in a specific namespace.

        :rtype: object
        :param self: self is an instance of the class.
        :param namespace: namespace.
        """
        exception_count = 3
        while True:
            try:
                api_response = self.core_v1.list_namespaced_pod(
                    namespace, label_selector="app, release")
            except Exception as e_obj:
                utilprocs.log(
                    (
                        "Exception when trying to list all "
                        "pod details in namespace: {}".format(e_obj)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            return api_response

    def get_pod_ip_address(self, name, namespace):
        """
        Obtains the ip address of the pod.

        :param name: pod name.
        :param namespace: namespace name
        """

#         utilprocs.log('Getting pod {} IP'.format(name))
        pod_addr = ''
        exception_count = 3
        while True:
            try:
                api_response = self.get_namespace_pod_details(namespace)
            except Exception as e_obj:
#                 utilprocs.log(
#                     (
#                         "Exception when trying obtain ip "
#                         "address of pod: {}".format(e_obj)
#                     )
#                 )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            break

        items = api_response.items
        print("items" + str(items))
        for item in items:
            print("item" + str(item))
            if name in item.metadata.name:
                print("name" + name)
                pod_addr = item.status.pod_ip
#                 utilprocs.log('ip: {}'.format(pod_addr))

        if pod_addr == '':
            raise RuntimeError('No ip address found for pod {}'.format(name))

        return pod_addr

    def get_namespaced_service_details(self, service, namespace):
        """
        Listing details of a service in a specific namespace.

        :param service: service name.
        :param namespace: namespace.
        """
        exception_count = 3
        while True:
            try:
                utilprocs.log('Getting details of {} service'.format(service))
                api_response = self.core_v1.list_namespaced_service(
                    namespace,
                    field_selector="metadata.name={}".format(service))
            except Exception as e_obj:
                utilprocs.log(
                    (
                        "Exception when trying to list details of "
                        "a service in namespace {}: {}".format(
                            namespace, e_obj)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            return api_response

    def get_service_cluster_ip(self, service, namespace):
        """
        Obtains the cluster ip of a service.

        :param service: service name.
        :param namespace: namespace.
        """
        utilprocs.log('Getting service {} Cluster IP'.format(service))

        cluster_ip = ''
        api_response = self.get_namespaced_service_details(service, namespace)
        items = api_response.items

        for item in items:
            if service in item.metadata.name:
                cluster_ip = item.spec.cluster_ip

        utilprocs.log(
            'Cluster ip of the service {}: {}'.format(service, cluster_ip))

        if cluster_ip == "":
            raise RuntimeError(
                'No cluster ip found for service {}'.format(service))

        return cluster_ip

    def delete_all_pvc_namespace(self, namespace):
        """
        Deletes all Persistent Volume Claims in the specific namespace.

        :param self: self is an instance of the class.
        :param namespace: namespace.
        """
        exception_count = 3
        while True:
            try:
                self.core_v1. \
                    delete_collection_namespaced_persistent_volume_claim(
                        namespace)
                break
            except Exception as e_obj:
                utilprocs.log(
                    (
                        "Exception when trying to delete "
                        "all Persistent Volume Claims "
                        "in namespace: {}".format(e_obj)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

        # keep it to 2 minutes so k8s has enough time to delete the pods
        # because deletion of the PVCs starts after pods deletion
        try_count = 24
        while try_count > 0:
            response = self.core_v1. \
                list_namespaced_persistent_volume_claim(namespace)
            if response.items:
                time.sleep(5)
                try_count -= 1
                continue

            utilprocs.log("All PVC's are no longer in namespace {}"
                          .format(namespace))
            break
        else:
            utilprocs.log("Timeout waiting for PVC's to terminate, they may "
                          "still be in namespace: {}".format(namespace))
            raise RuntimeError('Timeout waiting for PVC deletion')

    def exec_cmd_on_pod(self, name, namespace, command, container=''):
        """
        Executes commands on a given container of the pod.

        :param self: self is an instance of the class.
        :param name: name of the test pod.
        :param namespace: namespace.
        :param command: the command you wish to execute.
        :param container: the container you want to use.
        """

        exception_count = 3
        while True:
            try:
                api_response = self.core_v1.connect_get_namespaced_pod_exec
            except Exception as e_obj:
                utilprocs.log(
                    (
                        "Exception when trying to connect GET "
                        "requests to exec of Pod: {}".format(e_obj)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

            utilprocs.log('Executing {} on pod {}'.format(command, name))
            res = stream(api_response,
                         name, namespace, command=command,
                         container=container, stderr=True, stdin=False,
                         stdout=True, tty=False)
            utilprocs.log('Result: {}'.format(res))
            return res

    # Deprecated Functions
    def get_pod_ip(self, name):
        """
        Obtains the ip address of the pod.

        :param self: self is an instance of the class.
        :param name: pod name.
        """

        utilprocs.log('This function is deprecated. '
                      'Please use the get_pod_ip_address')
        utilprocs.log('Getting pod {} IP'.format(name))
        pod_addr = ''
        api_response = self.get_namespace_pod_details(name)
        exception_count = 3
        while True:
            try:
                api_response = self.get_namespace_pod_details(name)
            except Exception as e_obj:
                utilprocs.log(
                    (
                        "Exception when trying obtain ip "
                        "address of pod: {}".format(e_obj)
                    )
                )
                exception_count -= 1
                if exception_count <= 0:
                    raise
                continue

        items = api_response.items
        for item in items:
            if name in item.metadata.name:
                pod_addr = item.status.pod_ip
                utilprocs.log('ip: {}'.format(pod_addr))

        return pod_addr

    def shoot_pod(self, name, namespace):
        """
        Deletes the pod.

        :param self: self is an instance of the class.
        :param name: name of the pod to be deleted.
        :param namespace: namespace.
        """
        utilprocs.log('This function is deprecated. '
                      'Use delete_pod instead')

        self.delete_pod(
            name, namespace, wait_for_terminating=False)
