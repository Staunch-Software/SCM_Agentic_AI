# utils/exceptions.py
class AgentError(Exception):
    """Base exception for agent errors"""
    pass

class SessionNotFoundError(AgentError):
    """Session not found error"""
    pass

class DataLoadError(AgentError):
    """Data loading error"""
    pass

class OdooConnectionError(AgentError):
    """Odoo connection error"""
    pass

class OdooOperationError(AgentError):
    """Odoo operation error"""
    pass

class AIServiceError(AgentError):
    """AI service error"""
    pass

class TimeParsingError(AgentError):
    """Time parsing error"""
    pass

class PlanningError(AgentError):
    """Planning service error"""
    pass