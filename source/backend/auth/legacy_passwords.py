"""Bounded compatibility for explicitly imported bcrypt and Werkzeug hashes.

Weak unsalted SHA hashes, plaintext and unknown schemes require recovery.
Only successful verification permits rehashing to the current scrypt scheme.
"""
import re


def supported(encoded):
    value=str(encoded or '')
    if re.fullmatch(r'\$2[aby]\$(0[4-9]|1[0-6])\$[./A-Za-z0-9]{53}', value):
        return True
    if '$' not in value:
        return False
    method=value.split('$',1)[0].split(':')
    if len(method)==3 and method[:2] in [['pbkdf2','sha256'],['pbkdf2','sha512']]:
        return method[2].isdigit() and 1000<=int(method[2])<=2000000
    if len(method)==4 and method[0]=='scrypt' and all(p.isdigit() for p in method[1:]):
        n,r,p=map(int,method[1:])
        return n in {16384,32768,65536} and r==8 and p==1
    return False


def verify(password,encoded):
    if not supported(encoded) or not 1<=len(password)<=128:
        return False
    try:
        if encoded.startswith(('$2a$','$2b$','$2y$')):
            import bcrypt
            return len(password.encode())<=72 and bcrypt.checkpw(password.encode(),encoded.encode('ascii'))
        from werkzeug.security import check_password_hash
        return check_password_hash(encoded,password)
    except (ValueError,TypeError,OverflowError):
        return False
