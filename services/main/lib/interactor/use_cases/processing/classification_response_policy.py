from __future__ import annotations

from typing import Any

from thirdnews_contracts import CallbackResult

from lib.interactor.errors import ClassifierProtocolError


class ClassificationResponsePolicy:
    def failure(self, response: CallbackResult | Any) -> tuple[Exception, bool] | None:
        if response.error is not None:
            return (
                ClassifierProtocolError(f"classifier_failed:{response.error.code}"),
                bool(response.error.retryable),
            )
        trace = getattr(response, "trace", None)
        if trace is not None and trace.error:
            return ClassifierProtocolError("classifier_failed:trace_error"), True
        return None
