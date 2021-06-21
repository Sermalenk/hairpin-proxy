import logging
import time
from collections import defaultdict
from string import Template

from kubernetes import client, config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

INGRESS_ADDRESS = "hairpin-proxy.hairpin-proxy.svc.cluster.local"
COMMENT_LINE = "# Added by hairpin-proxy"
ZONE_TEMPLATE_FILE = "template.txt"
COREDNS_NAMESPACE = "kube-system"
COREDNS_CUSTOM_CONFIGMAP = "coredns-custom"
COREDNS_CUSTOM_FILENAME = "Corefile.custom"
SLEEP_PERIOD = 15


def create_template():
    with open(ZONE_TEMPLATE_FILE) as f:
        return Template(f.read())


ZONE_TEMPLATE = create_template()

config.load_incluster_config()


def extract_zones():
    zones = defaultdict(set)
    api = client.ExtensionsV1beta1Api()
    result = api.list_ingress_for_all_namespaces(watch=False)
    for item in result.items:
        for rule in item.spec.rules:
            zone = rule.host.split('.')[-1]
            zones[zone].add(rule.host)
    return zones


def make_host_line(host):
    return f"rewrite name {host} {INGRESS_ADDRESS} {COMMENT_LINE}"


def make_corefile(zones):
    zone_strs = []
    all_rewrites = []
    for zone, hosts in zones.items():
        hosts_rewrites = "\n    ".join(map(make_host_line, hosts))
        all_rewrites.append(hosts_rewrites)
        zone_strs.append(
            ZONE_TEMPLATE.substitute({"zone": zone, "rewrites": hosts_rewrites})
        )
    zone_strs.append(ZONE_TEMPLATE.substitute(
        {"zone": "svc.cluster.local", "rewrites": "\n    ".join(all_rewrites)}
    ))
    return "\n\n".join(zone_strs)


def get_existing_custom_corefile():
    api = client.CoreV1Api()
    try:
        config_map = api.read_namespaced_config_map(
            COREDNS_CUSTOM_CONFIGMAP, COREDNS_NAMESPACE
        )
    except client.ApiException as e:
        if e.status == 404:
            return None
        raise
    return config_map.data[COREDNS_CUSTOM_FILENAME]


def make_configmap_obj(file_content):
    metadata = client.V1ObjectMeta(name=COREDNS_CUSTOM_CONFIGMAP)
    return client.V1ConfigMap(
        metadata=metadata,
        data={
            COREDNS_CUSTOM_FILENAME: file_content
        }
    )


def loop():
    zones = extract_zones()
    new_file = make_corefile(zones)
    old_file = get_existing_custom_corefile()

    api = client.CoreV1Api()

    if old_file is None:
        config_map = make_configmap_obj(new_file)
        api.create_namespaced_config_map(
            COREDNS_NAMESPACE,
            config_map
        )
        logging.info(f"New applied Corefile.custom:\n{new_file}")
    elif new_file != old_file:
        config_map = make_configmap_obj(new_file)
        api.replace_namespaced_config_map(
            COREDNS_CUSTOM_CONFIGMAP,
            COREDNS_NAMESPACE,
            config_map
        )
        logging.info(f"New applied Corefile.custom:\n{new_file}")
    else:
        logging.info("Nothing changed")


if __name__ == "__main__":
    try:
        while True:
            try:
                loop()
            except KeyboardInterrupt:
                break
            except Exception as e:
                logging.exception(str(e))
            finally:
                time.sleep(SLEEP_PERIOD)
    except KeyboardInterrupt:
        logging.info("Finished")
