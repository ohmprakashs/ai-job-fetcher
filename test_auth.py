import urllib.request
import ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
print(urllib.request.urlopen("https://api.anthropic.com", context=ctx, timeout=5).getcode())
