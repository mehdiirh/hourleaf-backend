from django.utils.cache import add_never_cache_headers


class PrivateApiResponseMiddleware:
    """Do not let browsers/proxies retain account data, including token responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            add_never_cache_headers(response)
        return response
