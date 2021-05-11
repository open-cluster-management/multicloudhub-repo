#!/usr/bin/env python3
# Copyright (c) 2020 Red Hat, Inc.
# Copyright Contributors to the Open Cluster Management project
# Assumes: Python 3.6+

import argparse
import os
import shutil
import yaml
import array
import logging
from git import Repo

# Parse an image reference.
def parse_image_ref(image_ref):

   # Image ref:  [registry-and-ns/]repository-name[:tag][@digest]

   parsed_ref = dict()

   remaining_ref = image_ref
   at_pos = remaining_ref.rfind("@")
   if at_pos > 0:
      parsed_ref["digest"] = remaining_ref[at_pos+1:]
      remaining_ref = remaining_ref[0:at_pos]
   else:
      parsed_ref["digest"] = None
   colon_pos = remaining_ref.rfind(":")
   if colon_pos > 0:
      parsed_ref["tag"] = remaining_ref[colon_pos+1:]
      remaining_ref = remaining_ref[0:colon_pos]
   else:
      parsed_ref["tag"] = None
   slash_pos = remaining_ref.rfind("/")
   if slash_pos > 0:
      parsed_ref["repository"] = remaining_ref[slash_pos+1:]
      rgy_and_ns = remaining_ref[0:slash_pos]
   else:
      parsed_ref["repository"] = remaining_ref
      rgy_and_ns = "localhost"
   parsed_ref["registry_and_namespace"] = rgy_and_ns

   rgy, ns = split_at(rgy_and_ns, "/", favor_right=False)
   if not ns:
      ns = ""

   parsed_ref["registry"] = rgy
   parsed_ref["namespace"] = ns

   slash_pos = image_ref.rfind("/")
   if slash_pos > 0:
      repo_and_suffix = image_ref[slash_pos+1:]
   else:
      repo_and_suffix = image_ref
   parsed_ref["repository_and_suffix"]  = repo_and_suffix

   return parsed_ref

def templateHelmChart(helmChart):
    logging.info("Copying templates into new '%s' chart directory ...", helmChart)
    # Create main folder
    if os.path.exists(os.path.join("stable", helmChart)):
        logging.critical("Chart already exists with name '%s'", helmChart)
        exit(1)

    # Create Chart.yaml, values.yaml, and templates dir
    os.makedirs(os.path.join("stable", helmChart, "templates"))
    shutil.copyfile("chart-templates/Chart.yaml", os.path.join("stable", helmChart, "Chart.yaml"))
    shutil.copyfile("chart-templates/values.yaml", os.path.join("stable", helmChart, "values.yaml"))
    logging.info("Templates copied.\n")

def fillChartYaml(helmChart, csvPath):
    logging.info("Updating '%s' Chart.yaml file ...", helmChart)
    chartYml = os.path.join("stable", helmChart, "Chart.yaml")

    # Read Chart.yaml
    with open(chartYml, 'r') as f:
        chart = yaml.safe_load(f)

    # Read CSV    
    with open(csvPath, 'r') as f:
        csv = yaml.safe_load(f)

    logging.info("Chart Name: %s", helmChart)
    logging.info("Description: %s", csv["metadata"]["annotations"]["description"])

    # Write to Chart.yaml
    chart['name'] = helmChart
    chart['description'] = csv["metadata"]["annotations"]["description"]
    chart['version'] = csv['metadata']['name'].split(".", 1)[1][1:]
    with open(chartYml, 'w') as f:
        yaml.dump(chart, f)
    logging.info("'%s' Chart.yaml updated successfully.\n", helmChart)

def addDeployment(helmChart, deployment):
    name = deployment["name"]
    logging.info("Templating deployment '%s.yaml' ...", name)

    deployYaml = os.path.join("stable", helmChart, "templates",  name + ".yaml")
    shutil.copyfile("chart-templates/templates/deployment.yaml", deployYaml)

    with open(deployYaml, 'r') as f:
        deploy = yaml.safe_load(f)
        
    deploy['spec'] = deployment['spec']
    deploy['metadata']['name'] = name
    with open(deployYaml, 'w') as f:
        yaml.dump(deploy, f)
    logging.info("Deployment '%s.yaml' updated successfully.\n", name)

def addClusterScopedRBAC(helmChart, rbacMap):
    name = rbacMap["serviceAccountName"]
    # name = "not-default"
    
    logging.info("Setting cluster scoped RBAC ...")
    logging.info("Templating clusterrole '%s-clusterrole.yaml' ...", name)
    
    # Create Clusterrole
    clusterroleYaml = os.path.join("stable", helmChart, "templates",  name + "-clusterrole.yaml")
    shutil.copyfile("chart-templates/templates/clusterrole.yaml", clusterroleYaml)
    with open(clusterroleYaml, 'r') as f:
        clusterrole = yaml.safe_load(f)
    # Edit Clusterrole
    clusterrole["rules"] = rbacMap["rules"]
    clusterrole["metadata"]["name"] = name
    # Save Clusterrole
    with open(clusterroleYaml, 'w') as f:
        yaml.dump(clusterrole, f)
    logging.info("Clusterrole '%s-clusterrole.yaml' updated successfully.", name)
    
    logging.info("Templating serviceaccount '%s-serviceaccount.yaml' ...", name)
    # Create Serviceaccount
    serviceAccountYaml = os.path.join("stable", helmChart, "templates",  name + "-serviceaccount.yaml")
    shutil.copyfile("chart-templates/templates/serviceaccount.yaml", serviceAccountYaml)
    with open(serviceAccountYaml, 'r') as f:
        serviceAccount = yaml.safe_load(f)
    # Edit Serviceaccount
    serviceAccount["metadata"]["name"] = name
    # Save Serviceaccount
    with open(serviceAccountYaml, 'w') as f:
        yaml.dump(serviceAccount, f)
    logging.info("Serviceaccount '%s-serviceaccount.yaml' updated successfully.", name)

    logging.info("Templating clusterrolebinding '%s-clusterrolebinding.yaml' ...", name)
    # Create Clusterrolebinding
    clusterrolebindingYaml = os.path.join("stable", helmChart, "templates",  name + "-clusterrolebinding.yaml")
    shutil.copyfile("chart-templates/templates/clusterrolebinding.yaml", clusterrolebindingYaml)
    with open(clusterrolebindingYaml, 'r') as f:
        clusterrolebinding = yaml.safe_load(f)
    clusterrolebinding['metadata']['name'] = name
    clusterrolebinding['roleRef']['name'] = clusterrole["metadata"]["name"]
    clusterrolebinding['subjects'][0]['name'] = name
    with open(clusterrolebindingYaml, 'w') as f:
        yaml.dump(clusterrolebinding, f)
    logging.info("Clusterrolebinding '%s-clusterrolebinding.yaml' updated successfully.", name)
    logging.info("Cluster scoped RBAC created.\n")

def addNamespaceScopedRBAC(helmChart, rbacMap):
    name = rbacMap["serviceAccountName"]
    # name = "not-default"
    logging.info("Setting namespaced scoped RBAC ...")
    logging.info("Templating role '%s-role.yaml' ...", name)
    # Create role
    roleYaml = os.path.join("stable", helmChart, "templates",  name + "-role.yaml")
    shutil.copyfile("chart-templates/templates/role.yaml", roleYaml)
    with open(roleYaml, 'r') as f:
        role = yaml.safe_load(f)
    # Edit role
    role["rules"] = rbacMap["rules"]
    role["metadata"]["name"] = name
    # Save role
    with open(roleYaml, 'w') as f:
        yaml.dump(role, f)
    logging.info("Role '%s-role.yaml' updated successfully.", name)
    
    # Create Serviceaccount
    serviceAccountYaml = os.path.join("stable", helmChart, "templates",  name + "-serviceaccount.yaml")
    if not os.path.isfile(serviceAccountYaml):
        logging.info("Serviceaccount doesnt exist. Templating '%s-serviceaccount.yaml' ...", name)
        shutil.copyfile("chart-templates/templates/serviceaccount.yaml", serviceAccountYaml)
        with open(serviceAccountYaml, 'r') as f:
            serviceAccount = yaml.safe_load(f)
        # Edit Serviceaccount
        serviceAccount["metadata"]["name"] = name
        # Save Serviceaccount
        with open(serviceAccountYaml, 'w') as f:
            yaml.dump(serviceAccount, f)
        logging.info("Serviceaccount '%s-serviceaccount.yaml' updated successfully.", name)

    logging.info("Templating rolebinding '%s-rolebinding.yaml' ...", name)
    # Create rolebinding
    rolebindingYaml = os.path.join("stable", helmChart, "templates",  name + "-rolebinding.yaml")
    shutil.copyfile("chart-templates/templates/rolebinding.yaml", rolebindingYaml)
    with open(rolebindingYaml, 'r') as f:
        rolebinding = yaml.safe_load(f)
    rolebinding['metadata']['name'] = name
    rolebinding['roleRef']['name'] = role["metadata"]["name"] = name
    rolebinding['subjects'][0]['name'] = name
    with open(rolebindingYaml, 'w') as f:
        yaml.dump(rolebinding, f)
    logging.info("Rolebinding '%s-rolebinding.yaml' updated successfully.", name)
    logging.info("Namespace scoped RBAC created.\n")

def addResources(helmChart, csvPath):
    logging.info("Reading CSV '%s'\n", csvPath)

    # Read CSV    
    with open(csvPath, 'r') as f:
        csv = yaml.safe_load(f)

    logging.info("Checking for deployments, clusterpermissions, and permissions.\n")
    deployments = csv['spec']['install']['spec']['deployments']    

    for deployment in deployments:
        addDeployment(helmChart, deployment)
    
    if 'clusterPermissions' in csv['spec']['install']['spec']:
        clusterPermissions = csv['spec']['install']['spec']['clusterPermissions']
        for clusterRole in clusterPermissions:
            addClusterScopedRBAC(helmChart, clusterRole)

    if 'permissions' in csv['spec']['install']['spec']:
        permissions = csv['spec']['install']['spec']['permissions']
        for role in permissions:
            addNamespaceScopedRBAC(helmChart, role)
    
    
    logging.info("Resources have been successfully added to chart '%s' from CSV '%s'.\n", helmChart, csvPath)

def findTemplatesOfType(helmChart, kind):
    resources = []
    for filename in os.listdir(os.path.join("stable", helmChart, "templates")):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            filePath = os.path.join("stable", helmChart, "templates", filename)
            with open(filePath, 'r') as f:
                fileYml = yaml.safe_load(f)
            if fileYml['kind'] == kind:
                resources.append(filePath)
            continue
        else:
            continue
    return resources

def fixImageReferences(helmChart, imageKeyMapping):
    logging.info("Fixing image and pull policy references in deployments and values.yaml ...")
    valuesYaml = os.path.join("stable", helmChart, "values.yaml")
    with open(valuesYaml, 'r') as f:
        values = yaml.safe_load(f)
    
    deployments = findTemplatesOfType(helmChart, 'Deployment')
    imageKeys = []
    for deployment in deployments:
        with open(deployment, 'r') as f:
            deploy = yaml.safe_load(f)
        
        containers = deploy['spec']['template']['spec']['containers']
        for container in containers:
            image_key = parse_image_ref(container['image'])["repository"]
            print(image_key)
            try:
                image_key = imageKeyMapping[image_key]
            except KeyError:
                logging.critical("No image key mapping provided for imageKey: %s" % image_key)
                exit(1)
            image_key = image_key.replace('-', '_')
            imageKeys.append(image_key)
            container['image'] = "{{ .Values.global.imageOverrides." + image_key + " }}"
            container['imagePullPolicy'] = "{{ .Values.global.pullPolicy }}"
        with open(deployment, 'w') as f:
            yaml.dump(deploy, f)

    del  values['global']['imageOverrides']['imageOverride']
    for imageKey in imageKeys:
        values['global']['imageOverrides'][imageKey] = ""
    with open(valuesYaml, 'w') as f:
        yaml.dump(values, f)
    logging.info("Image references and pull policy in deployments and values.yaml updated successfully.\n")

def injectHelmFlowControl(deployment):
    logging.info("Adding Helm flow control for NodeSelector and Proxy Overrides ...")
    deploy = open(deployment, "r")
    lines = deploy.readlines()
    for i, line in enumerate(lines):
        if line.strip() == "nodeSelector: \'\'":
            lines[i] = """{{- with .Values.hubconfig.nodeSelector }}
      nodeSelector:
{{ toYaml . | indent 8 }}
{{- end }}
"""
        if line.strip() == "env:" or line.strip() == "env: {}":
            lines[i] = """        env:
{{- if .Values.hubconfig.proxyConfigs }}
        - name: HTTP_PROXY
          value: {{ .Values.hubconfig.proxyConfigs.HTTP_PROXY }}
        - name: HTTPS_PROXY
          value: {{ .Values.hubconfig.proxyConfigs.HTTPS_PROXY }}
        - name: NO_PROXY
          value: {{ .Values.hubconfig.proxyConfigs.NO_PROXY }}
{{- end }}
"""
        a_file = open(deployment, "w")
        a_file.writelines(lines)
        a_file.close()
    logging.info("Added Helm flow control for NodeSelector and Proxy Overrides.\n")


def updateDeployments(helmChart):
    logging.info("Updating deployments with antiaffinity, security policies, and tolerations ...")
    deploySpecYaml = "chart-templates/templates/deploymentspec.yaml"
    with open(deploySpecYaml, 'r') as f:
        deploySpec = yaml.safe_load(f)
    
    deployments = findTemplatesOfType(helmChart, 'Deployment')
    for deployment in deployments:
        with open(deployment, 'r') as f:
            deploy = yaml.safe_load(f)
        affinityList = deploySpec['affinity']['podAntiAffinity']['preferredDuringSchedulingIgnoredDuringExecution']
        for antiaffinity in affinityList:
            antiaffinity['podAffinityTerm']['labelSelector']['matchExpressions'][0]['values'][0] = deploy['metadata']['name']
        deploy['spec']['template']['spec']['affinity'] = deploySpec['affinity']
        deploy['spec']['template']['spec']['tolerations'] = deploySpec['tolerations']
        deploy['spec']['template']['spec']['hostNetwork'] = False
        deploy['spec']['template']['spec']['hostPID'] = False
        deploy['spec']['template']['spec']['hostIPC'] = False
        if 'securityContext' not in deploy['spec']['template']['spec']:
            deploy['spec']['template']['spec']['securityContext'] = {}
        deploy['spec']['template']['spec']['securityContext']['runAsNonRoot'] = True
        deploy['spec']['template']['metadata']['labels']['ocm-antiaffinity-selector'] = deploy['metadata']['name']
        deploy['spec']['template']['spec']['nodeSelector'] = ""

        containers = deploy['spec']['template']['spec']['containers']
        for container in containers:
            if 'securityContext' not in container: 
                container['securityContext'] = {}
            if 'env' not in container: 
                container['env'] = {}
            container['securityContext']['allowPrivilegeEscalation'] = False
            container['securityContext']['capabilities'] = {}
            container['securityContext']['capabilities']['drop'] = ['ALL']
            container['securityContext']['privileged'] = False
            container['securityContext']['readOnlyRootFilesystem'] = True
        
        with open(deployment, 'w') as f:
            yaml.dump(deploy, f)
        logging.info("Deployments updated with antiaffinity, security policies, and tolerations successfully. \n")

        injectHelmFlowControl(deployment)


def updateRBAC(helmChart):
    logging.info("Updating Clusterroles, roles, clusterrolebindings, and rolebindings ...")
    clusterroles = findTemplatesOfType(helmChart, 'ClusterRole')
    roles = findTemplatesOfType(helmChart, 'Role')
    clusterrolebindings = findTemplatesOfType(helmChart, 'ClusterRoleBinding')
    rolebindings = findTemplatesOfType(helmChart, 'RoleBinding')

    for rbacFile in clusterroles + roles + clusterrolebindings + rolebindings:
        with open(rbacFile, 'r') as f:
            rbac = yaml.safe_load(f)
        rbac['metadata']['name'] = "{{ .Values.org }}:{{ .Release.Name }}:" + rbac['metadata']['name']
        if rbac['kind'] in ['RoleBinding', 'ClusterRoleBinding']:
            rbac['roleRef']['name'] = "{{ .Values.org }}:{{ .Release.Name }}:" + rbac['roleRef']['name']
        with open(rbacFile, 'w') as f:
            yaml.dump(rbac, f)
    logging.info("Clusterroles, roles, clusterrolebindings, and rolebindings updated. \n")


def injectRequirements(helmChart, imageKeyMapping):
    logging.info("Updating Helm chart '%s' with onboarding requirements ...", helmChart)
    fixImageReferences(helmChart, imageKeyMapping)
    updateRBAC(helmChart)
    updateDeployments(helmChart)
    logging.info("Updated Chart '%s' successfully\n", helmChart)

def split_at(the_str, the_delim, favor_right=True):

   split_pos = the_str.find(the_delim)
   if split_pos > 0:
      left_part  = the_str[0:split_pos]
      right_part = the_str[split_pos+1:]
   else:
      if favor_right:
         left_part  = None
         right_part = the_str
      else:
         left_part  = the_str
         right_part = None

   return (left_part, right_part)

def getCSVPath(repo, operator):
    packageYmlPath = os.path.join("tmp", repo, operator["package-yml"])
    if not os.path.exists(packageYmlPath):
        logging.critical("Could not find package.yaml at given path:", operator["package-yml"])
        exit(1)

    with open(packageYmlPath, 'r') as f:
        packageYml = yaml.safe_load(f)

    bundlePath = ""
    for channel in packageYml["channels"]:
        if channel["name"] == operator["channel"]:
            version = channel["currentCSV"].split(".", 1)[1][1:]
            bundlePath = os.path.join("tmp", repo, os.path.dirname(operator["package-yml"]), version)
            break

    if bundlePath == "":
        print("Unable to find given channel: " +  operator["channel"] + " in package.yaml: " + operator["package-yml"])
        exit(1)

    for filename in os.listdir(bundlePath):
        if not filename.endswith(".yaml"): 
            continue
        filepath = os.path.join(bundlePath, filename)
        with open(filepath, 'r') as f:
            resourceFile = yaml.safe_load(f)

        if resourceFile["kind"] == "ClusterServiceVersion":
            return filepath

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skipOverrides", dest="skipOverrides", type=bool)
    parser.set_defaults(skipOverrides=False)

    args = parser.parse_args()
    skipOverrides = args.skipOverrides

    logging.basicConfig(level=logging.DEBUG)

    configYaml = "config.yaml"
    with open(configYaml, 'r') as f:
        config = yaml.safe_load(f)

    for repo in config:
        csvPath = ""
        logging.info("Cloning: %s", repo["repo_name"])
        repo_path = os.path.join(os.getcwd(), "tmp/" + repo["repo_name"])
        if not os.path.exists(repo_path):
            Repo.clone_from(repo["github_ref"], repo_path)

        for operator in repo["operators"]:
            logging.info("Helm Chartifying -  %s!\n", operator["name"])
            csvPath = getCSVPath(repo["repo_name"], operator)

            if csvPath == "":
                print("Unable to find given channel: " +  operator["channel"] + " in package.yaml: " + operator["package-yml"])
                exit(1)

            logging.basicConfig(level=logging.DEBUG)

            logging.info("Reading CSV: %s ...",  csvPath)
            # Checks CSV exists
            if not os.path.isfile(csvPath):
                logging.critical("Unable to find CSV at given path - '" + csvPath + "'.")
                exit(1)

            with open(csvPath, 'r') as f:
                csv = yaml.safe_load(f)
            
            helmChart = csv['metadata']['name'].split(".")[0]
            logging.info("Creating helm chart: '%s' ...", helmChart)

            # Prepares Helm Chart Directory
            logging.info("Templating helm chart '%s' ...", helmChart)
            templateHelmChart(helmChart)

            logging.info("Filling Chart.yaml ...")
            fillChartYaml(helmChart, csvPath)

            logging.info("Adding Resources from CSV...")
            addResources(helmChart, csvPath)
            logging.info("Resources have been added from CSV. \n")

            if not skipOverrides:
                logging.info("Adding Overrides (set --skipOverrides=true to skip) ...")
                injectRequirements(helmChart, operator["imageMappings"])
                logging.info("Overrides added. \n")

if __name__ == "__main__":
   main()
