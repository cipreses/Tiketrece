from django.shortcuts import redirect

class AprobacionGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            if request.user.estado_aprobacion != 'aprobado':
                path = request.path
                if not (
                    path.startswith('/cuenta-pendiente') or
                    path.startswith('/auth/') or
                    path.startswith('/static/') or
                    path.startswith('/admin/')
                ):
                    return redirect('cuenta_pendiente')

        return self.get_response(request)
