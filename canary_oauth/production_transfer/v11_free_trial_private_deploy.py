#!/usr/bin/env python3
"""V11 single-service Free Trial gate. Default read-only. No production mutation.

This script DOES NOT machine-verify Free Trial status: the Google Cloud Billing
API billingEnabled field is not a proof of a Free Trial account. The dated
operator UI attestation below is deliberately short-lived and fail-closed.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

PROJECT = 'project-4e9f56f4-a524-4759-91f'
BILLING = 'billingAccounts/01117F-2FB3E2-31D263'
REGION = 'europe-west1'
PRODUCTION = 'c-lab-gcp-control'
TEST = 'c-lab-oauth-v11-test'
IMAGE = ('ghcr.io/donaldshim/clab-oauth-v11-synthetic@sha256:'
         'a2e28d9c746073b9455c0a75e03bcf2892f3b0bf8339d5990759da27121b9d64')
EVIDENCE_DATE = dt.date(2026, 10, 27)
TRIAL_END = dt.date(2026, 12, 17)
TRIAL_CREDIT_USD_AT_EVIDENCE = 198.88

class GateError(Exception):
    pass

def gcloud(*args, allow_missing=False):
    p = subprocess.run(['gcloud', *args], capture_output=True, text=True, timeout=80)
    if p.returncode:
        msg = p.stderr[:600]
        if allow_missing and ('NOT_FOUND' in msg or 'not found' in msg.lower()):
            return None
        raise GateError('GCLOUD_READ_OR_ACTION_FAILED: ' + ' '.join(args[:4]) + ': ' + msg)
    return p.stdout

def gjson(*args, allow_missing=False):
    s = gcloud(*args, '--format=json', allow_missing=allow_missing)
    return json.loads(s) if s is not None else None

def service(name):
    return gjson('run', 'services', 'describe', name,
                 '--project='+PROJECT, '--region='+REGION, allow_missing=True)

def service_policy(name):
    return gjson('run', 'services', 'get-iam-policy', name,
                 '--project='+PROJECT, '--region='+REGION)

def live_snapshot(name):
    s = service(name)
    if not s:
        raise GateError('EXPECTED_PRODUCTION_SERVICE_MISSING')
    status = s.get('status', {})
    return {
        'name': s.get('metadata', {}).get('name'),
        'ready_revision': status.get('latestReadyRevisionName'),
        'traffic': status.get('traffic'),
        'url': status.get('url'),
        'iam': service_policy(name),
    }

def account_check():
    if dt.datetime.now(dt.timezone.utc).date() != EVIDENCE_DATE:
        raise GateError('DATED_FREE_TRIAL_UI_EVIDENCE_EXPIRED: need a fresh operator review')
    if not TRIAL_END > EVIDENCE_DATE or TRIAL_CREDIT_USD_AT_EVIDENCE < 5:
        raise GateError('TRIAL_EVIDENCE_NOT_ADMISSIBLE')
    active_project = gcloud('config', 'get-value', 'project').strip()
    if active_project != PROJECT:
        raise GateError('WRONG_GCLOUD_PROJECT')
    billing = gjson('billing', 'projects', 'describe', PROJECT)
    if billing.get('billingEnabled') is not True or billing.get('billingAccountName') != BILLING:
        raise GateError('BILLING_LINK_OR_ENABLED_STATE_MISMATCH')
    return {'current_project': PROJECT, 'billing_link': BILLING,
            'trial_ui_evidence_date': EVIDENCE_DATE.isoformat(),
            'trial_expires': TRIAL_END.isoformat(),
            'trial_credit_at_ui_evidence': TRIAL_CREDIT_USD_AT_EVIDENCE,
            'financial_policy': 'NO_CARD_CHARGE_FREE_TRIAL_ONLY',
            'warning': 'Billing project API cannot certify trial vs paid. Operator screenshot required today.'}

def preflight(selected_test_sa=None):
    finance = account_check()
    sa_list = gjson('iam', 'service-accounts', 'list', '--project='+PROJECT)
    accounts = [x['email'] for x in sa_list if x.get('email', '').endswith('@'+PROJECT+'.iam.gserviceaccount.com')
                and 'v11' in x['email'].split('@')[0] and 'test' in x['email'].split('@')[0]]
    accounts = sorted(set(accounts))
    if selected_test_sa is not None:
        if selected_test_sa not in accounts:
            raise GateError('EXPLICIT_V11_TEST_IDENTITY_NOT_FOUND_OR_INVALID: '+selected_test_sa)
        sa = selected_test_sa
    elif len(accounts) == 1:
        sa = accounts[0]
    else:
        raise GateError('V11_TEST_IDENTITY_AMBIGUOUS: found '+str(len(accounts))+
                        '; candidates='+','.join(accounts)+
                        '; select one exact email with --test-service-account only after IAM review')
    policy = gjson('projects', 'get-iam-policy', PROJECT)
    project_bindings = [b['role'] for b in policy.get('bindings', [])
                        if 'serviceAccount:'+sa in b.get('members', [])]
    if project_bindings:
        raise GateError('TEST_IDENTITY_HAS_PROJECT_LEVEL_ROLES: '+','.join(project_bindings))
    services = gjson('run', 'services', 'list', '--project='+PROJECT, '--region='+REGION)
    names = [x.get('metadata', {}).get('name', x.get('name', '').split('/')[-1]) for x in services]
    if TEST in names:
        raise GateError('TEST_SERVICE_ALREADY_EXISTS_NO_OVERWRITE')
    if PRODUCTION not in names:
        raise GateError('PRODUCTION_SERVICE_NOT_VISIBLE')
    # The test identity must not already be used by another Cloud Run service.
    users = [n for n, x in zip(names, services) if x.get('spec', {}).get('template', {}).get('spec', {}).get('serviceAccountName') == sa]
    if users:
        raise GateError('TEST_IDENTITY_ALREADY_USED: '+','.join(users))
    production_before = live_snapshot(PRODUCTION)
    if production_before['name'] != PRODUCTION:
        raise GateError('PRODUCTION_IDENTITY_MISMATCH')
    return {'finance': finance, 'service_account': sa, 'production_before': production_before}

def verify_test(sa):
    obj = service(TEST)
    if not obj or obj.get('metadata', {}).get('name') != TEST:
        raise GateError('TEST_SERVICE_NOT_CREATED')
    spec = obj.get('spec', {}).get('template', {}).get('spec', {})
    if spec.get('serviceAccountName') != sa:
        raise GateError('TEST_IDENTITY_MISMATCH')
    containers = spec.get('containers', [])
    if len(containers) != 1 or containers[0].get('image') != IMAGE:
        raise GateError('TEST_IMAGE_DIGEST_MISMATCH')
    pol = service_policy(TEST)
    if any('allUsers' in b.get('members', []) or 'allAuthenticatedUsers' in b.get('members', [])
           for b in pol.get('bindings', [])):
        raise GateError('TEST_SERVICE_HAS_PUBLIC_INVOKER')
    traffic = obj.get('status', {}).get('traffic', [])
    if any(x.get('percent', 0) != 0 for x in traffic):
        raise GateError('TEST_SERVICE_TRAFFIC_NONZERO')
    if not any(x.get('tag') == 'v11-synthetic' for x in traffic):
        raise GateError('TEST_TAG_NOT_PRESENT')
    return {'name': TEST, 'image': IMAGE, 'sa': sa, 'traffic': traffic,
            'ready_revision': obj.get('status', {}).get('latestReadyRevisionName'),
            'public_invoker': False}

def deploy(sa):
    return gcloud('run','deploy',TEST,
        '--project='+PROJECT, '--region='+REGION, '--image='+IMAGE,
        '--service-account='+sa, '--no-allow-unauthenticated',
        '--ingress=all', '--min-instances=0', '--max-instances=1',
        '--cpu=1', '--memory=256Mi', '--concurrency=1', '--timeout=15s',
        '--cpu-throttling', '--tag=v11-synthetic', '--no-traffic',
        '--set-env-vars=C_LAB_V11_SYNTHETIC_ONLY=1,C_LAB_V11_ISSUER=https://oauth-v11.invalid',
        '--quiet')

def rollback_test():
    if service(TEST) is not None:
        gcloud('run','services','delete',TEST,'--project='+PROJECT,
               '--region='+REGION,'--quiet')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--execute', action='store_true', help='Execute test-only Cloud Run deployment')
    ap.add_argument('--test-service-account', type=str, default=None,
                    help='Exact v11-test service identity after read-only IAM audit')
    ap.add_argument('--accept-trial-credit', action='store_true',
                    help='Acknowledge: trial credit may be spent; no claim of Always Free')
    args = ap.parse_args()
    result = {'schema':'C_LAB_OAUTH_V11_TRIAL_PRIVATE_DEPLOY_GATE_V1',
              'utc':dt.datetime.now(dt.timezone.utc).isoformat(),
              'executed':False, 'production_changed_by_script':False,
              'target_service':TEST, 'image':IMAGE}
    output = Path.home()/'c-lab-v11-artifacts'/'V11_TRIAL_GATE_RECEIPT_20261027.json'
    output.parent.mkdir(exist_ok=True)
    try:
        result['preflight'] = preflight(args.test_service_account)
        result['state'] = 'PREFLIGHT_PASS_READ_ONLY'
        if args.execute:
            if not args.accept_trial_credit:
                raise GateError('EXPLICIT_TRIAL_CREDIT_ACCEPTANCE_REQUIRED')
            # Check for race: fail if the test service appeared since preflight.
            if service(TEST) is not None:
                raise GateError('SERVICE_CREATED_CONCURRENTLY')
            result['deployment_attempted'] = True
            deploy(result['preflight']['service_account'])
            result['test_after'] = verify_test(result['preflight']['service_account'])
            production_after = live_snapshot(PRODUCTION)
            if production_after != result['preflight']['production_before']:
                raise GateError('PRODUCTION_READBACK_DRIFT')
            result['production_after'] = production_after
            result['state'] = 'PRIVATE_TEST_SERVICE_DEPLOYED_TAG_0PCT'
            result['executed'] = True
    except Exception as exc:
        result['error'] = type(exc).__name__+': '+str(exc)
        result['state'] = 'STOP_GATE_OR_DEPLOY_FAILURE'
        if args.execute and result.get('deployment_attempted'):
            try:
                rollback_test()
                result['rollback'] = 'TEST_SERVICE_DELETE_COMPLETED'
            except Exception as re:
                result['rollback'] = 'ROLLBACK_OPEN: '+type(re).__name__+': '+str(re)
    finally:
        # Snapshot contains Cloud Run service IAM policies; keep local and restricted.
        output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)+'\n')
        try: os.chmod(output, 0o600)
        except OSError: pass
        print(json.dumps({'state':result['state'], 'receipt':str(output),
                          'error':result.get('error'), 'rollback':result.get('rollback')}))
    return 0 if result['state'] in ('PREFLIGHT_PASS_READ_ONLY', 'PRIVATE_TEST_SERVICE_DEPLOYED_TAG_0PCT') else 2

if __name__ == '__main__':
    sys.exit(main())
