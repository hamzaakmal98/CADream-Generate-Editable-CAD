import json
import pathlib
import uuid
import urllib.request
import urllib.error

p = pathlib.Path('../../sample-files/Input_Sample_0.dxf').resolve()
payload = {
    'total_pages': 49,
    'cad_ir': None,
    'site_placements': {
        'schema_version': 'v1',
        'entities': {'bess': [], 'poi': None, 'cable_paths': []},
    },
    'sld_session': {
        'schema_version': 'sld-v1',
        'nodes': [],
        'edges': [],
        'tool_settings': {'tool_mode': 'select', 'viewport': {'scale': 1, 'pos': {'x': 0, 'y': 0}}},
    },
    'right_panel_metadata': {
        'ac_system_size': '380kW',
        'inverter_model': 'Dynapower CPS1250',
        'dc_system_size': '760kWh',
        'bess_model': 'Gotion Edge 760',
        'customer_website': '',
        'customer_phone': '',
        'customer_contact': '',
        'ahj': '',
        'designer_company': 'CADream',
        'designer_address': '',
        'designer_website': '',
        'designer_phone': '',
        'designer_contact': '',
        'page_notes': '',
        'sheet_metadata': {
            'scale': 'As Noted',
            'sheet_title': '',
            'drawn_by': 'DG',
            'checked_by': 'DG',
            'approved_by': 'A',
            'issue_date': '2026-03-03',
            'sheet_number': '01',
            'revision': 'A',
        },
        'title_block': {
            'project_name': '',
            'client_name': '',
            'site_address': '',
            'drawn_by': 'DG',
            'checked_by': 'DG',
            'approved_by': 'A',
        },
        'engineer_signature_image': {'uri': '', 'mime_type': '', 'base64': ''},
    },
}

boundary = '----WebKitFormBoundary' + uuid.uuid4().hex
parts = []

def add_field(name: str, value: str) -> None:
    parts.append(f'--{boundary}\r\n'.encode())
    parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
    parts.append(value.encode())
    parts.append(b'\r\n')

def add_file(name: str, filename: str, data: bytes, content_type: str) -> None:
    parts.append(f'--{boundary}\r\n'.encode())
    parts.append(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode())
    parts.append(f'Content-Type: {content_type}\r\n\r\n'.encode())
    parts.append(data)
    parts.append(b'\r\n')

add_field('payload_json', json.dumps(payload))
add_file('file', p.name, p.read_bytes(), 'application/dxf')
parts.append(f'--{boundary}--\r\n'.encode())
body = b''.join(parts)

req = urllib.request.Request(
    'http://127.0.0.1:8000/planset/pages/full-from-source/pdf-export',
    data=body,
    method='POST',
    headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
)

try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        print(resp.status)
        print(resp.read(200))
except urllib.error.HTTPError as e:
    print(e.code)
    print(e.read().decode('utf-8', 'ignore'))
