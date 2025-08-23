# utils/response_formatter.py
class ResponseFormatter:
    def format_response(self, response: str) -> str:
        if self._is_tabular_response(response):
            return self._format_tabular_response(response)
        return response

    def _is_tabular_response(self, response: str) -> bool:
        return ("Here are the" in response and
                ("planned_order_id" in response or "display_name" in response))

    def _format_tabular_response(self, response: str) -> str:
        parts = response.split('\n', 1)
        if len(parts) > 1:
            return f"{parts[0]}\n```\n{parts[1]}\n```"
        return response