'''Class to provide namespace manipulation.
'''

import time
from kubernetes.client.rest import ApiException
from kubernetes import client

from ..utils import (get_execution_namespace, make_logger)


class LSSTNamespaceManager(object):
    '''Class to provide namespace manipulation.
    '''
    namespace = None
    service_account = None

    def __init__(self, *args, **kwargs):
        self.log = make_logger()
        self.log.debug("Creating LSSTNamespaceManager")
        self.parent = kwargs.pop('parent')

    def update_namespace_name(self):
        '''Build namespace name from user and execution namespace.
        '''
        execution_namespace = get_execution_namespace()
        self.log.debug("Execution namespace: '{}'".format(execution_namespace))
        user = self.parent.user
        self.log.debug("User: '{}'".format(user))
        username = user.escaped_name
        if execution_namespace and username:
            self.namespace = "{}-{}".format(execution_namespace,
                                            username)
        else:
            df_msg = "Using 'default' namespace."
            self.log.warning(df_msg)
            self.namespace = "default"

    def ensure_namespace(self):
        '''Here we make sure that the namespace exists, creating it if
        it does not.  That requires a ClusterRole that can list and create
        namespaces.

        If we have shadow PVs, we clone the (static) NFS PVs and then
        attach namespaced PVCs to them.  Thus the role needs to be
        able to list and create PVs and PVCs.

        If we create the namespace, we also create (if needed) a ServiceAccount
        within it to allow the user pod to spawn dask and workflow pods.

        '''
        self.update_namespace_name()
        namespace = self.namespace
        api = self.parent.api
        if namespace == "default":
            self.log.warning("Namespace is 'default'; no manipulation.")
            return
        ns = client.V1Namespace(
            metadata=client.V1ObjectMeta(name=namespace))
        try:
            self.log.info("Attempting to create namespace '%s'" % namespace)
            api.create_namespace(ns)
        except ApiException as e:
            if e.status != 409:
                estr = "Create namespace '%s' failed: %s" % (ns, str(e))
                self.log.exception(estr)
                raise
            else:
                self.log.info("Namespace '%s' already exists." % namespace)
        # Wait for the namespace to actually appear before creating objects
        #  in it.
        self._wait_for_namespace()
        if self.service_account:
            self.log.debug("Ensuring namespaced service account.")
            self._ensure_namespaced_service_account()
        else:
            self.log.debug("No namespaced service account required.")
        if self.parent.spawner.enable_namespace_quotas:
            self.log.debug("Determining resource quota.")
            qm = self.parent.quota_mgr
            quota = qm.get_resource_quota_spec()
            if quota:
                self.log.debug("Ensuring namespace quota.")
                qm.ensure_namespaced_resource_quota(quota)
            else:
                self.log.debug("No namespace quota required.")
        self.log.debug("Namespace resources ensured.")

    def _define_namespaced_account_objects(self):
        # We may want these when and if we move Argo workflows into the
        #  deployment.
        #
        #    client.V1PolicyRule(
        #        api_groups=["argoproj.io"],
        #        resources=["workflows", "workflows/finalizers"],
        #        verbs=["get", "list", "watch", "update", "patch", "delete"]
        #    ),
        #    client.V1PolicyRule(
        #        api_groups=["argoproj.io"],
        #        resources=["workflowtemplates",
        #                   "workflowtemplates/finalizers"],
        #        verbs=["get", "list", "watch"],
        #    ),
        #
        #    client.V1PolicyRule(
        #        api_groups=[""],
        #        resources=["secrets"],
        #        verbs=["get"]
        #    ),
        #    client.V1PolicyRule(
        #        api_groups=[""],
        #        resources=["configmaps"],
        #        verbs=["list"]
        #    ),
        namespace = self.namespace
        account = self.service_account
        if not account:
            self.log.info("No service account defined.")
            return (None, None, None)
        md = client.V1ObjectMeta(name=account)
        svcacct = client.V1ServiceAccount(metadata=md)
        rules = [
            client.V1PolicyRule(
                api_groups=[""],
                resources=["pods", "services"],
                verbs=["get", "list", "watch", "create", "delete"]
            ),
            client.V1PolicyRule(
                api_groups=[""],
                resources=["pods/log", "serviceaccounts"],
                verbs=["get", "list"]
            ),
        ]
        role = client.V1Role(
            rules=rules,
            metadata=md)
        rolebinding = client.V1RoleBinding(
            metadata=md,
            role_ref=client.V1RoleRef(api_group="rbac.authorization.k8s.io",
                                      kind="Role",
                                      name=account),
            subjects=[client.V1Subject(
                kind="ServiceAccount",
                name=account,
                namespace=namespace)]
        )

        return svcacct, role, rolebinding

    def _ensure_namespaced_service_account(self):
        # Create a service account with role and rolebinding to allow it
        #  to manipulate pods in the namespace.
        self.log.info("Ensuring namespaced service account.")
        namespace = self.namespace
        api = self.parent.api
        rbac_api = self.parent.rbac_api
        account = self.service_account
        svcacct, role, rolebinding = self._define_namespaced_account_objects()
        if not svcacct:
            self.log.info("Service account not defined.")
            return
        try:
            self.log.info("Attempting to create service account.")
            api.create_namespaced_service_account(
                namespace=namespace,
                body=svcacct)
        except ApiException as e:
            if e.status != 409:
                self.log.exception("Create service account '%s' " % account +
                                   "in namespace '%s' " % namespace +
                                   "failed: %s" % str(e))
                raise
            else:
                self.log.info("Service account '%s' " % account +
                              "in namespace '%s' already exists." % namespace)
        try:
            self.log.info("Attempting to create role in namespace.")
            rbac_api.create_namespaced_role(
                namespace,
                role)
        except ApiException as e:
            if e.status != 409:
                self.log.exception("Create role '%s' " % account +
                                   "in namespace '%s' " % namespace +
                                   "failed: %s" % str(e))
                raise
            else:
                self.log.info("Role '%s' " % account +
                              "already exists in namespace '%s'." % namespace)
        try:
            self.log.info("Attempting to create rolebinding in namespace.")
            rbac_api.create_namespaced_role_binding(
                namespace,
                rolebinding)
        except ApiException as e:
            if e.status != 409:
                self.log.exception("Create rolebinding '%s'" % account +
                                   "in namespace '%s' " % namespace +
                                   "failed: %s", str(e))
                raise
            else:
                self.log.info("Rolebinding '%s' " % account +
                              "already exists in '%s'." % namespace)

    def _wait_for_namespace(self, timeout=30):
        '''Wait for namespace to be created.'''
        namespace = self.namespace
        if namespace == "default":
            return  # Default doesn't get manipulated
        for dl in range(timeout):
            self.log.debug("Checking for namespace " +
                           "{} [{}/{}]".format(self.namespace, dl, timeout))
            nl = self.parent.api.list_namespace(timeout_seconds=1)
            for ns in nl.items:
                nsname = ns.metadata.name
                if nsname == namespace:
                    self.log.debug("Namespace {} found.".format(namespace))
                    return
                self.log.debug("Namespace {} not present yet.")
            time.sleep(1)
        raise RuntimeError(
            "Namespace '{}' was not created in {} seconds!".format(namespace,
                                                                   timeout))

    def maybe_delete_namespace(self):
        '''Here we try to delete the namespace.  If it has no non-dask
        running pods, and it's not the default namespace, we can delete it."

        This requires a cluster role that can delete namespaces.'''
        self.log.debug("Attempting to delete namespace.")
        namespace = self.namespace
        if namespace == "default":
            self.log.warning("Cannot delete 'default' namespace")
            return
        podlist = self.parent.api.list_namespaced_pod(namespace)
        clear_to_delete = True
        if podlist and podlist.items and len(podlist.items) > 0:
            clear_to_delete = self._check_pods(podlist.items)
        if not clear_to_delete:
            self.log.info("Not deleting namespace '%s'" % namespace)
            return False
        self.log.info("Clear to delete namespace '%s'" % namespace)
        self.log.info("Deleting namespace '%s'" % namespace)
        self.parent.api.delete_namespace(namespace)
        return True

    def _check_pods(self, items):
        namespace = self.namespace
        for i in items:
            if i and i.status:
                phase = i.status.phase
                if (phase == "Running" or phase == "Unknown"
                        or phase == "Pending"):
                    pname = i.metadata.name
                    if pname.startswith("dask-"):
                        # We can murder abandoned dask pods
                        continue
                    self.log.info("Pod in state '%s'; " % phase +
                                  "cannot delete namespace '%s'." % namespace)
                    return False
        return True

    def destroy_namespaced_resource_quota(self):
        '''Remove quotas from namespace.
        You don't usually have to call this, since it will get
        cleaned up as part of namespace deletion.
        '''
        namespace = self.get_user_namespace()
        api = self.parent.api
        qname = "quota-" + namespace
        dopts = client.V1DeleteOptions()
        self.log.info("Deleting resourcequota '%s'" % qname)
        api.delete_namespaced_resource_quota(qname, namespace, dopts)

    def delete_namespaced_service_account_objects(self):
        '''Remove service accounts, roles, and rolebindings from namespace.
        You don't usually have to call this, since they will get
         cleaned up as part of namespace deletion.
        '''
        namespace = self.get_user_namespace()
        account = self.service_account
        if not account:
            self.log.info("Service account not defined.")
            return
        dopts = client.V1DeleteOptions()
        self.log.info("Deleting service accounts/role/rolebinding " +
                      "for %s" % namespace)
        self.parent.rbac_api.delete_namespaced_role_binding(
            account,
            namespace,
            dopts)
        self.parent.rbac_api.delete_namespaced_role(
            account,
            namespace,
            dopts)
        self.parent.api.delete_namespaced_service_account(
            account,
            namespace,
            dopts)
