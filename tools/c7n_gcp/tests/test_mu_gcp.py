# Copyright 2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import time

from c7n.testing import functional
from c7n_gcp import mu
from gcp_common import BaseTest


HELLO_WORLD = """\
def handler(event, context):
    print("gcf handler invoke %s" % event)
"""


class FunctionTest(BaseTest):

    def get_function(self, events=(), factory=None, **kw):
        if not events:
            assert factory
            events = [mu.HTTPEvent(factory)]
        config = dict(
            name="custodian-dev",
            labels=[],
            runtime='python37',
            events=events)
        config.update(kw)
        archive = mu.custodian_archive()
        archive.close()
        return mu.CloudFunction(config, archive)

    def test_deploy_function(self):
        factory = self.replay_flight_data('mu-deploy')
        manager = mu.CloudFunctionManager(factory)
        func = self.get_function(factory=factory)
        manager.publish(func)
        func_info = manager.get(func.name)
        self.assertTrue(func_info['httpsTrigger'])
        self.assertEqual(func_info['status'], 'DEPLOY_IN_PROGRESS')
        self.assertEqual(
            func_info['name'],
            'projects/custodian-1291/locations/us-central1/functions/custodian-dev')

    @functional
    def test_api_subscriber(self):
        # integration styled..

        factory = self.replay_flight_data('mu-api-subscriber')
        p = self.load_policy(
            {'name': 'topic-created',
             'resource': 'gcp.pubsub-topic',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': ['google.pubsub.v1.Publisher.CreateTopic']}},
            session_factory=factory)

        # Create all policy resources.
        p.provision()

        session = factory()
        project_id = session.get_default_project()
        region = 'us-central1'
        func_client = session.client('cloudfunctions', 'v1', 'projects.locations.functions')
        pubsub_client = session.client('pubsub', 'v1', 'projects.topics')
        sink_client = session.client('logging', 'v2', 'projects.sinks')

        # Check on the resources for the api subscription

        # check function exists
        func_info = func_client.execute_command(
            'get', {'name': 'projects/{}/locations/{}/functions/topic-created'.format(
                project_id, region)})
        self.assertEqual(
            func_info['eventTrigger']['eventType'],
            'providers/cloud.pubsub/eventTypes/topic.publish')
        self.assertEqual(
            func_info['eventTrigger']['resource'],
            'projects/{}/topics/custodian-auto-audit-topic-created'.format(
                project_id))

        # check sink exists
        sink = sink_client.execute_command(
            'get', {'sinkName': 'projects/{}/sinks/custodian-auto-audit-topic-created'.format(
                project_id)})
        self.assertEqual(
            sink['destination'],
            'pubsub.googleapis.com/projects/{}/topics/custodian-auto-audit-topic-created'.format(
                project_id))

        # check the topic iam policy
        topic_policy = pubsub_client.execute_command(
            'getIamPolicy', {
                'resource': 'projects/{}/topics/custodian-auto-audit-topic-created'.format(
                    project_id)})
        self.assertEqual(
            topic_policy['bindings'],
            [{u'role': u'roles/pubsub.publisher', u'members': [sink['writerIdentity']]}])

        # todo set this up as test cleanups, dependent on ordering at the moment, fifo atm
        # it appears, we want lifo.
        if self.recording:
            # we sleep to allow time for in progress operations on creation to complete
            # function requirements building primarily.
            time.sleep(42)
        p.get_execution_mode().deprovision()
