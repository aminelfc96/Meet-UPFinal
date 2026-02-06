# test_imports.py - Test import structure

try:
    print("Testing imports...")
    
    # Test database imports
    from database import DIContainer, User, UserRepository
    print("✅ Database imports working")
    
    # Test services imports
    from services import AuthService, get_auth_service, LoginRequest
    print("✅ Services imports working")
    
    # Test config imports
    from config_manager import get_config
    print("✅ Config imports working")
    
    # Test error handler imports
    from error_handler import AppError, ValidationError
    print("✅ Error handler imports working")
    
    # Test enhanced auth imports (without circular dependencies)
    from enhanced_auth import JWTManager
    print("✅ Enhanced auth imports working")
    
    print("\n🎉 All imports successful! Architecture is properly structured.")
    print("The application should work once FastAPI is installed.")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
except Exception as e:
    print(f"❌ Unexpected error: {e}")