"""Read-only Cloud admission gate for isolated C-Lab Gateway (no secrets revealed)."""
from __future__ import annotations
import argparse, json, subprocess
from datetime import datetime, timezone

PROJECT = 'project-4e9f56f4-a524-4759-91f'
REGION = 'europe-west1'
PROD = 'c-lab-gcp-control'
PROD_REV = 'c-lab-gcp-control-custody-v1-prod-20261020'
SERVICE = 'c-lab-oauth-gateway-v1'
SA = f'{SERVICE}@{PROJECT}.iam.gserviceaccount.com'
BILLING = 'billingAccounts/01117F-2FB3E2-31D263'
NEEDED = ('c-lab-oauth-gateway-v1-fernet',
          'c-lab-oauth-gateway-v1-google-client-secret',
          'c-lab-oauth-gateway-v1-database-url')


def call(*args):
    proc = subprocess.run(['gcloud', *args], capture_output=True, text=True,
                          timeout=25, check=False)
    if proc.returncode:
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


def audit():
    gates = {}
    billing = call('billing', 'projects', 'describe', PROJECT, '--format=json')
    gates['billing_link'] = (isinstance(billing, dict)
                             and billing.get('billingEnabled') is True
                             and billing.get('billingAccountName') == BILLING)
    # The billing API never proves unupgraded Free Trial or available trial balance.
    gates['free_trial_current_ui'] = False
    identity = call('iam', 'service-accounts', 'describe', SA,
                    f'--project={PROJECT}', '--format=json')
    gates['identity'] = isinstance(identity, dict) and identity.get('email') == SA and not identity.get('disabled')
    policy = call('projects', 'get-iam-policy', PROJECT, '--format=json')
    principal = 'serviceAccount:' + SA
    gates['no_project_iam_grants'] = (isinstance(policy, dict)
        and all(principal not in (binding.get('members') or [])
                for binding in policy.get('bindings', [])))
    prod = call('run', 'services', 'describe', PROD,
                f'--project={PROJECT}', f'--region={REGION}', '--format=json')
    gates['production_revision_unchanged'] = (isinstance(prod, dict)
        and (prod.get('status') or {}).get('latestReadyRevisionName') == PROD_REV)
    services = call('run', 'services', 'list', f'--project={PROJECT}',
                    f'--region={REGION}', '--format=json')
    gates['gateway_target_absent'] = (isinstance(services, list)
        and not any((entry.get('metadata') or {}).get('name') == SERVICE for entry in services))
    secrets = call('secrets', 'list', f'--project={PROJECT}', '--format=json')
    for name in NEEDED:
        exists = (isinstance(secrets, list) and any(
            (s.get('name') or '').split('/')[-1] == name for s in secrets))
        versions = call('secrets', 'versions', 'list', name,
                        f'--project={PROJECT}', '--format=json') if exists else None
        gates['secret_ready_' + name] = bool(exists and isinstance(versions,list)
            and any(v.get('state') == 'ENABLED' for v in versions))
    sqlapi = call('services', 'list', f'--project={PROJECT}',
                  '--enabled', '--format=json')
    gates['sqladmin_api_enabled'] = (isinstance(sqlapi,list) and any(
        (x.get('config') or {}).get('name') == 'sqladmin.googleapis.com'
        for x in sqlapi))
    # A free, expiring Render database cannot be treated as persistent production DB.
    gates['dedicated_postgres_and_backup_certified'] = False
    gates['google_client_redirect_registered'] = False
    gates['real_google_refresh_test'] = False
    gates['chatgpt_native_post_expiry_test'] = False
    return {'schema': 'CLAB_OAUTH_GATEWAY_DEPLOY_GATE_V1',
            'checked_utc': datetime.now(timezone.utc).isoformat(),
            'side_effects': 'NONE', 'secret_values_read': False,
            'gates': gates, 'state': 'AFFIRMED' if all(gates.values()) else 'OPEN'}


def main():
    ap = argparse.ArgumentParser(description='Read-only C-Lab OAuth Gateway admission audit')
    ap.add_argument('--output', default='GATEWAY_ADMISSION_READBACK.json')
    args=ap.parse_args()
    result=audit()
    with open(args.output,'w',encoding='utf-8') as fh:
        json.dump(result,fh,ensure_ascii=False,indent=2)
    print(f"{result['state']} / {sum(result['gates'].values())}/{len(result['gates'])} gates / NO WRITES / NO SECRET READ")
    print('Unclosed: ' + ', '.join(k for k,v in result['gates'].items() if not v))
    return 0 if result['state']=='AFFIRMED' else 2

if __name__ == '__main__':
    raise SystemExit(main())
