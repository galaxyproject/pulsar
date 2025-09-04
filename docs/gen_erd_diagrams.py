import os
import sys

import erdantic as erd

sys.path.insert(1, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from pulsar.client.container_job_config import GcpJobParams

DOC_SOURCE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__)))
class_to_diagram = {
    GcpJobParams: "job_destination_parameters_gcp",
}

for clazz, diagram_name in class_to_diagram.items():
    erd.draw(clazz, out=f"{DOC_SOURCE_DIR}/{diagram_name}.png")