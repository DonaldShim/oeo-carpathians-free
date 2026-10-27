import importlib.util
from pathlib import Path
from unittest.mock import patch
import sys
source = Path(__file__).with_name('v11_free_trial_private_deploy.py')
if not source.exists(): source = Path(__file__).parent.parent / 'v11_free_trial_private_deploy.py'
spec = importlib.util.spec_from_file_location('gate', str(source))
gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)

class MockG:
    def __init__(self, billing_enabled=True, sa_roles=None, target=False, public=False, prod_drift=False, two_identities=False):
        self.calls=[]; self.billing_enabled=billing_enabled; self.sa_roles=sa_roles or []; self.target=target; self.public=public; self.prod_drift=prod_drift; self.two_identities=two_identities
        self.sa='c-lab-oauth-v11-test@'+gate.PROJECT+'.iam.gserviceaccount.com'
    def cmd(self,*a,allow_missing=False):
        self.calls.append(a)
        if a[:3]==('config','get-value','project'):return gate.PROJECT
        if a[:3]==('run','deploy',gate.TEST):
            self.target=True;return 'deployed'
        if a[:3]==('run','services','delete'):self.target=False;return 'deleted'
        raise AssertionError(a)
    def json(self,*a,allow_missing=False):
        self.calls.append(a)
        if a[:3]==('billing','projects','describe'):
            return {'billingEnabled':self.billing_enabled,'billingAccountName':gate.BILLING}
        if a[:3]==('iam','service-accounts','list'):
            return [{'email':self.sa}]+([{'email':'c-lab-oauth-v11-test-extra@'+gate.PROJECT+'.iam.gserviceaccount.com'}] if self.two_identities else [])
        if a[:2]==('projects','get-iam-policy'):
            return {'bindings':[{'role':role,'members':['serviceAccount:'+self.sa]} for role in self.sa_roles]}
        if a[:3]==('run','services','list'):
            return [{'metadata':{'name':gate.PRODUCTION},'spec':{'template':{'spec':{'serviceAccountName':'prod@something'}}}}] + ([{'metadata':{'name':gate.TEST}}] if self.target else [])
        if a[:3]==('run','services','describe'):
            if a[3]==gate.TEST and not self.target:return None
            if a[3]==gate.PRODUCTION:
                return {'metadata':{'name':gate.PRODUCTION},'status':{'latestReadyRevisionName':'r1' if not self.prod_drift else 'r2','traffic':[{'percent':100,'revisionName':'r1'}], 'url':'http://p'}}
            if a[3]==gate.TEST:
                return {'metadata':{'name':gate.TEST},'spec':{'template':{'spec':{'serviceAccountName':self.sa,'containers':[{'image':gate.IMAGE}]}}},'status':{'traffic':[{'tag':'v11-synthetic','percent':0}],'latestReadyRevisionName':'t1'}}
        if a[:3]==('run','services','get-iam-policy'):
            return {'bindings':([{'role':'roles/run.invoker','members':['allUsers']}] if self.public and a[3]==gate.TEST else [])}
        raise AssertionError(a)

def ck(fn):
    fn()
    print('PASS '+fn.__name__)

@patch.object(gate,'gcloud')
@patch.object(gate,'gjson')
def check_good_preflight(j,c):
    m=MockG();j.side_effect=m.json;c.side_effect=m.cmd
    v=gate.preflight()
    assert v['service_account']==m.sa
    assert v['finance']['financial_policy']=='NO_CARD_CHARGE_FREE_TRIAL_ONLY'

@patch.object(gate,'gcloud')
@patch.object(gate,'gjson')
def check_fail_paid_billing_link(j,c):
    m=MockG(billing_enabled=False);j.side_effect=m.json;c.side_effect=m.cmd
    try:gate.preflight();assert False
    except gate.GateError as e:assert 'BILLING_LINK' in str(e)

@patch.object(gate,'gcloud')
@patch.object(gate,'gjson')
def check_fail_broad_sa_role(j,c):
    m=MockG(sa_roles=['roles/editor']);j.side_effect=m.json;c.side_effect=m.cmd
    try:gate.preflight();assert False
    except gate.GateError as e:assert 'PROJECT_LEVEL_ROLES' in str(e)

@patch.object(gate,'gcloud')
@patch.object(gate,'gjson')
def check_fail_existing_target(j,c):
    m=MockG(target=True);j.side_effect=m.json;c.side_effect=m.cmd
    try:gate.preflight();assert False
    except gate.GateError as e:assert 'EXISTS' in str(e)

@patch.object(gate,'gcloud')
@patch.object(gate,'gjson')
def check_test_private_verify(j,c):
    m=MockG(target=True);j.side_effect=m.json;c.side_effect=m.cmd
    assert gate.verify_test(m.sa)['public_invoker'] is False

@patch.object(gate,'gcloud')
@patch.object(gate,'gjson')
def check_test_public_rejected(j,c):
    m=MockG(target=True,public=True);j.side_effect=m.json;c.side_effect=m.cmd
    try:gate.verify_test(m.sa);assert False
    except gate.GateError as e:assert 'PUBLIC' in str(e)

@patch.object(gate,'gcloud')
@patch.object(gate,'gjson')
def check_rollback_only_target(j,c):
    m=MockG(target=True);j.side_effect=m.json;c.side_effect=m.cmd
    gate.rollback_test()
    assert m.target is False
    assert all(gate.PRODUCTION not in a for a in m.calls if a[:3]==('run','services','delete'))

@patch.object(gate,'gcloud')
@patch.object(gate,'gjson')
def check_image_pin_and_tag(j,c):
    m=MockG();j.side_effect=m.json;c.side_effect=m.cmd
    gate.deploy(m.sa)
    arg=m.calls[-1]
    for kw in ('--no-allow-unauthenticated','--no-traffic','--tag=v11-synthetic','--max-instances=1','--min-instances=0'):
        assert kw in arg
    assert '--image='+gate.IMAGE in arg

@patch.object(gate,'gcloud')
@patch.object(gate,'gjson')
def check_two_identities_fail_closed(j,c):
    m=MockG(two_identities=True); j.side_effect=m.json; c.side_effect=m.cmd
    try: gate.preflight(); assert False
    except gate.GateError as e:
        assert 'V11_TEST_IDENTITY_AMBIGUOUS' in str(e)
        assert m.sa in str(e)

@patch.object(gate,'gcloud')
@patch.object(gate,'gjson')
def check_explicit_pinned_identity(j,c):
    m=MockG(two_identities=True); j.side_effect=m.json; c.side_effect=m.cmd
    assert gate.preflight(m.sa)['service_account']==m.sa

@patch.object(gate,'gcloud')
@patch.object(gate,'gjson')
def check_unknown_identity_fails_closed(j,c):
    m=MockG(two_identities=True); j.side_effect=m.json; c.side_effect=m.cmd
    try: gate.preflight('bad@example.com'); assert False
    except gate.GateError as e: assert 'EXPLICIT_V11_TEST_IDENTITY_NOT_FOUND' in str(e)

for name in list(globals()):
    if name.startswith('check_'):
        ck(globals()[name])
print('11/11 MOCK PASS')