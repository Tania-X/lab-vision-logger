#!/bin/bash
# 测试运行脚本 - 运行所有SeekDB相关的测试

set -e

echo "=== 运行Lab-Log SeekDB相关测试 ==="

# 检查Python环境
if ! command -v python &> /dev/null; then
    echo "❌ Python未找到，请安装Python 3.10+"
    exit 1
fi

# 检查pytest是否安装
if ! python -m pytest --version &> /dev/null; then
    echo "❌ pytest未安装，正在安装..."
    pip install pytest pytest-mock pytest-asyncio pytest-cov
fi

# 创建测试覆盖率目录
mkdir -p htmlcov

echo "运行单元测试..."
python -m pytest tests/test_seekdb_client.py -v

echo "运行Web API测试..."
python -m pytest tests/test_web_api_auth.py tests/test_web_api_users.py -v

echo "运行管理员API测试..."
python -m pytest tests/test_web_api_admin.py -v

echo "运行紧急事件API测试..."
python -m pytest tests/test_web_api_emergencies.py -v

echo "运行编排管道测试..."
python -m pytest tests/test_orchestration.py -v

echo "运行日志写入器测试..."
python -m pytest tests/test_log_writer.py -v

echo "运行流媒体服务器测试..."
python -m pytest tests/test_streaming_server.py -v

echo "生成测试覆盖率报告..."
python -m pytest --cov=lab_log --cov-report=html --cov-report=term-missing --cov-fail-under=70

echo ""
echo "=== 测试完成 ==="
echo "📊 覆盖率报告: htmlcov/index.html"
echo "✅ 所有SeekDB相关功能测试通过！"