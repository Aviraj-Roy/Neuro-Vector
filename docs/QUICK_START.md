# 🎯 Quick Reference - Backend Execution

## ✅ CORRECT Execution Method

**ALWAYS run the backend using module execution:**

```bash
python -m backend.main
```

## ❌ WRONG Methods (DO NOT USE)

```bash
# ❌ Direct script execution
python backend/main.py

# ❌ Changing directory first
cd backend
python main.py

# ❌ Running from backend directory
cd backend
python -m main
```

## 🔍 Why Module Execution?

Module execution (`python -m`) ensures:

1. **Correct Import Paths**: All `from app.xxx import yyy` statements work
2. **Absolute Path Resolution**: Files are found regardless of CWD
3. **Dependency Validation**: Startup checks run automatically
4. **Reproducibility**: Works identically on all machines

## 📋 Pre-Flight Checklist

Before running, verify:

```bash
# 1. Virtual environment is activated
where python  # Should show venv path

# 2. Dependencies are installed
pip list | findstr fastapi

# 3. MongoDB is running
mongosh --eval "db.version()"

# 4. You're in project root
pwd  # Should end with Neuro-Vector-Backend
```

## 🚀 Complete Workflow

```bash
# 1. Navigate to project root
cd "c:\Users\royav\Downloads\Guwahati Refinery Internship ✅\NeuroVector\Neuro-Vector-Backend"

# 2. Activate virtual environment
venv\Scripts\activate

# 3. Run backend
python -m backend.main
```

## 🧪 Testing

### Test Dependency Checker

```bash
python -m backend.app.utils.dependency_check
```

**Expected:** All green checkmarks.

### Test Backend

```bash
python -m backend.main
```

**Expected:** Processes Apollo.pdf successfully.

## 📚 Documentation

- **Complete Setup**: See `REPRODUCIBLE_SETUP.md`
- **Root Cause Analysis**: See `DIAGNOSIS_AND_FIXES.md`
- **Fix Summary**: See `FIX_SUMMARY.md`
- **Original Guide**: See `BACKEND_RUN_GUIDE.md`

## 🆘 Troubleshooting

### "No module named 'app'"

**Fix:** Use module execution from project root:
```bash
cd "c:\Users\royav\Downloads\Guwahati Refinery Internship ✅\NeuroVector\Neuro-Vector-Backend"
python -m backend.main
```

### "Unable to read image"

**Fix:** Ensure using module execution (not direct script):
```bash
python -m backend.main  # ✅ Correct
```

### "No module named 'fastapi'"

**Fix:** Install dependencies:
```bash
pip install -r backend/requirements.txt
```

---

**Last Updated**: 2026-02-03  
**Version**: 2.0.0
