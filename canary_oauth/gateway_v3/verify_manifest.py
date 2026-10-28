import hashlib,json,pathlib
root=pathlib.Path(__file__).parent
m=json.loads((root/'SHA256_MANIFEST_V3.json').read_text())
for name,expected in m['files'].items():
    p=(root/name).resolve()
    assert p.is_relative_to(root.resolve()) and p.is_file(),name
    assert hashlib.sha256(p.read_bytes()).hexdigest()==expected,name
print('V3 manifest verified:',len(m['files']))
