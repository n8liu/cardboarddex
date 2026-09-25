import importlib.util
from pathlib import Path
import httpx

spec = importlib.util.spec_from_file_location('provision_images', Path(__file__).with_name('provision.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_existing_zone_rules_are_not_replaced():
    calls = []
    def handler(request):
        path = request.url.path
        calls.append((request.method, path, request.content))
        result = {}
        if path.endswith('/zones/zone'):
            result = {'name':'cardboarddex.app','account':{'id':'account'}}
        elif path.endswith('/domains/custom'):
            result = {'domains': []}
        elif path.endswith('/domains/custom/images.cardboarddex.app'):
            result = {'enabled': True}
        elif path.endswith('/entrypoint'):
            result = {'id':'existing', 'rules':[{'id':'unrelated', 'ref':'unrelated'}]}
        return httpx.Response(200, json={'success': True, 'result':result})
    with httpx.Client(base_url='https://api.cloudflare.com/client/v4', transport=httpx.MockTransport(handler)) as client:
        module.configure(client, 'account','zone')
    writes = [(method,path) for method,path,_ in calls if method != 'GET']
    assert ('POST','/client/v4/zones/zone/rulesets/existing/rules') in writes
    assert not any(path.endswith('/rulesets/existing') for _,path in writes)
    assert not any('unrelated' in path for _,path in writes)
