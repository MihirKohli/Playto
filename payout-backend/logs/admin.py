from django.contrib import admin
from .models import LogEntry


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display    = ['created_at', 'level', 'logger_name', 'message_preview', 'module', 'func_name', 'line_no']
    list_filter     = ['level', 'logger_name', 'created_at']
    search_fields   = ['message', 'logger_name', 'module']
    readonly_fields = ['level', 'logger_name', 'message', 'module', 'func_name', 'line_no', 'context', 'created_at']
    ordering        = ['-created_at']

    def message_preview(self, obj):
        return obj.message[:100] + '…' if len(obj.message) > 100 else obj.message
    message_preview.short_description = 'Message'

    def has_add_permission(self, request):        return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
