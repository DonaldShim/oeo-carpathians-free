from unittest.mock import patch
from gateway import deploy_gate as g

def test_everything_missing_fails_closed():
    with patch.object(g,'call',return_value=None):
        x=g.audit()
    assert x['state']=='OPEN'
    assert not any(x['gates'].values())
    assert x['side_effects']=='NONE' and x['secret_values_read'] is False

def test_even_full_readback_does_not_pretend_to_certify_oauth_or_trial():
    def mocked(*args):
        if args[:3]==('billing','projects','describe'):
            return {'billingEnabled':True,'billingAccountName':g.BILLING}
        if args[:3]==('iam','service-accounts','describe'):
            return {'email':g.SA,'disabled':False}
        if args[:2]==('projects','get-iam-policy'):return {'bindings':[]}
        if args[:3]==('run','services','describe'):
            return {'status':{'latestReadyRevisionName':g.PROD_REV}}
        if args[:3]==('run','services','list'):return []
        if args[:2]==('secrets','list'):
            return [{'name':'projects/test/secrets/'+x} for x in g.NEEDED]
        if args[:3]==('secrets','versions','list'):return [{'state':'ENABLED'}]
        if args[:2]==('services','list'):
            return [{'config':{'name':'sqladmin.googleapis.com'}}]
        raise AssertionError(args)
    with patch.object(g,'call',side_effect=mocked):x=g.audit()
    assert x['gates']['billing_link']
    assert x['gates']['no_project_iam_grants']
    assert x['gates']['secret_ready_c-lab-oauth-gateway-v1-fernet']
    assert not x['gates']['google_client_redirect_registered']
    assert not x['gates']['chatgpt_native_post_expiry_test']
    assert not x['gates']['free_trial_current_ui']
    assert x['state']=='OPEN'

def test_service_exists_blocks_creation():
    def mocked(*args):
        if args[:3]==('run','services','list'):
            return [{'metadata':{'name':g.SERVICE}}]
        return None
    with patch.object(g,'call',side_effect=mocked):x=g.audit()
    assert not x['gates']['gateway_target_absent']
