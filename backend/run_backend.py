import sys

# PyInstaller 兼容性：必須在導入其他模塊之前執行
if getattr(sys, 'frozen', False):
    # 運行在 PyInstaller 打包環境中
    import inspect
    
    _original_getsource = inspect.getsource
    _original_getsourcelines = inspect.getsourcelines
    _original_findsource = inspect.findsource
    
    def _getsource_fallback(obj):
        try:
            return _original_getsource(obj)
        except (OSError, TypeError):
            return f"# Source not available\n"
    
    def _getsourcelines_fallback(obj):
        try:
            return _original_getsourcelines(obj)
        except (OSError, TypeError):
            return (["# Source not available\n"], 0)
    
    def _findsource_fallback(obj):
        try:
            return _original_findsource(obj)
        except (OSError, TypeError):
            return (["# Source not available\n"], 0)
    
    inspect.getsource = _getsource_fallback
    inspect.getsourcelines = _getsourcelines_fallback
    inspect.findsource = _findsource_fallback
    

from uvicorn import run
from main import app
 
if __name__ == "__main__":
	run(app, host="0.0.0.0", port=54321, log_level="info") 