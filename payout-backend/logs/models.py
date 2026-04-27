from django.db import models


class LogEntry(models.Model):
    DEBUG    = 'DEBUG'
    INFO     = 'INFO'
    WARNING  = 'WARNING'
    ERROR    = 'ERROR'
    CRITICAL = 'CRITICAL'

    LEVEL_CHOICES = [
        (DEBUG,    'Debug'),
        (INFO,     'Info'),
        (WARNING,  'Warning'),
        (ERROR,    'Error'),
        (CRITICAL, 'Critical'),
    ]

    level       = models.CharField(max_length=10, choices=LEVEL_CHOICES, db_index=True)
    logger_name = models.CharField(max_length=200)
    message     = models.TextField()
    module      = models.CharField(max_length=200, blank=True)
    func_name   = models.CharField(max_length=200, blank=True)
    line_no     = models.IntegerField(null=True)
    context     = models.JSONField(default=dict, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'log entries'

    def __str__(self):
        return f'[{self.level}] {self.logger_name} — {self.message[:80]}'
