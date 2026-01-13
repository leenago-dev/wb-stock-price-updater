"""커스텀 예외 클래스 정의"""


class StockPriceUpdaterException(Exception):
    """기본 예외 클래스"""
    pass


class YahooFinanceException(StockPriceUpdaterException):
    """Yahoo Finance API 관련 예외"""
    pass


class SupabaseException(StockPriceUpdaterException):
    """Supabase 관련 예외"""
    pass


class RateLimitException(StockPriceUpdaterException):
    """Rate limit 관련 예외"""
    pass


class AuthenticationException(StockPriceUpdaterException):
    """인증 관련 예외"""
    pass


class ValidationException(StockPriceUpdaterException):
    """데이터 검증 관련 예외"""
    pass
