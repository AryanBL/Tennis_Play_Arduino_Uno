import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .serial_bridge import bridge


@require_GET
def index(request):
    bridge.start()
    return render(request, "game/index.html")


@require_GET
def state(request):
    bridge.start()
    return JsonResponse(bridge.snapshot())


@csrf_exempt
@require_POST
def keyboard(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
        sensor = int(payload["sensor"])
        speed = float(payload["speed"])
        if sensor not in range(4) or not 0.0 <= speed <= 250.0:
            raise ValueError
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": "Invalid sensor command"}, status=400)
    return JsonResponse({"ok": bridge.send_keyboard(sensor, speed)})
