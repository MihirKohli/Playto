from rest_framework.views import APIView
from rest_framework.response import Response
from .models import LogEntry


class LogListView(APIView):
    def get(self, request):
        qs = LogEntry.objects.all()

        level       = request.query_params.get('level')
        logger_name = request.query_params.get('logger')
        limit       = int(request.query_params.get('limit', 100))

        if level:
            qs = qs.filter(level=level.upper())
        if logger_name:
            qs = qs.filter(logger_name__icontains=logger_name)

        entries = qs[:limit]

        data = [
            {
                'id':          e.id,
                'level':       e.level,
                'logger_name': e.logger_name,
                'message':     e.message,
                'module':      e.module,
                'func_name':   e.func_name,
                'line_no':     e.line_no,
                'context':     e.context,
                'created_at':  e.created_at,
            }
            for e in entries
        ]

        return Response({'count': len(data), 'results': data})
