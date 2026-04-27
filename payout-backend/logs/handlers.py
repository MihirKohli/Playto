import logging
import concurrent.futures

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)


class DatabaseHandler(logging.Handler):
    def emit(self, record):
        _executor.submit(
            self._write,
            record.levelname,
            record.name,
            record.getMessage(),
            record.module,
            record.funcName,
            record.lineno,
            getattr(record, 'context', {}),
        )

    def _write(self, level, logger_name, message, module, func_name, line_no, context):
        try:
            from logs.models import LogEntry
            LogEntry.objects.create(
                level=level,
                logger_name=logger_name,
                message=message,
                module=module,
                func_name=func_name,
                line_no=line_no,
                context=context,
            )
        except Exception:
            pass
