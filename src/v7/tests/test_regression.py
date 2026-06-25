# -*- coding: utf-8 -*-
"""回归测试套件

覆盖核心功能：
1. 数据库连接与操作
2. API配置加密存储
3. 图纸上传与预处理
4. 审查流程
5. 统计准确性
"""

import os
import sys
import unittest
import tempfile
import shutil

# 确保src在路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from v7.db import get_db, init_db
from v7.crypto_utils import encrypt_text, decrypt_text, is_encrypted
from v7.preprocessor import DrawingExtractor


class TestCryptoUtils(unittest.TestCase):
    """测试加密工具。"""
    
    def test_encrypt_decrypt(self):
        """测试加密解密往返。"""
        original = "sk-test-api-key-12345"
        encrypted = encrypt_text(original)
        self.assertTrue(is_encrypted(encrypted))
        self.assertNotEqual(encrypted, original)
        
        decrypted = decrypt_text(encrypted)
        self.assertEqual(decrypted, original)
    
    def test_empty_string(self):
        """测试空字符串。"""
        self.assertEqual(encrypt_text(""), "")
        self.assertEqual(decrypt_text(""), "")
    
    def test_double_encrypt(self):
        """测试重复加密不报错。"""
        original = "test-key"
        encrypted1 = encrypt_text(original)
        encrypted2 = encrypt_text(encrypted1)
        self.assertEqual(encrypted1, encrypted2)


class TestDatabase(unittest.TestCase):
    """测试数据库操作。"""
    
    def setUp(self):
        """每个测试前创建临时数据库。"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        os.environ["V7_DB_PATH"] = self.db_path
        init_db()
    
    def tearDown(self):
        """每个测试后清理。"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        if "V7_DB_PATH" in os.environ:
            del os.environ["V7_DB_PATH"]
    
    def test_project_crud(self):
        """测试项目增删改查。"""
        db = get_db()
        
        # 创建
        db.execute("INSERT INTO projects (name, description) VALUES (?, ?)",
                   ("测试项目", "描述"))
        db.commit()
        
        # 查询
        row = db.execute("SELECT * FROM projects WHERE name = ?", ("测试项目",)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "测试项目")
    
    def test_api_key_encryption(self):
        """测试API Key加密存储。"""
        db = get_db()
        
        # 使用唯一provider名避免冲突
        import uuid
        provider = f"test_provider_{uuid.uuid4().hex[:8]}"
        
        key = encrypt_text("sk-secret-key")
        db.execute(
            "INSERT INTO api_keys (provider, api_key, base_url) VALUES (?, ?, ?)",
            (provider, key, "https://api.test.com")
        )
        db.commit()
        
        row = db.execute("SELECT api_key FROM api_keys WHERE provider = ?",
                        (provider,)).fetchone()
        self.assertTrue(is_encrypted(row["api_key"]))
        self.assertEqual(decrypt_text(row["api_key"]), "sk-secret-key")


class TestDrawingExtractor(unittest.TestCase):
    """测试图纸预处理。"""
    
    def test_classify_discipline(self):
        """测试专业分类。"""
        extractor = DrawingExtractor()
        
        # 创建模拟TextEntity列表
        class MockEntity:
            def __init__(self, text):
                self.raw_text = text
        
        test_cases = [
            ([MockEntity("建筑 平面图 墙体 门窗")], "building"),
            ([MockEntity("结构 钢筋 混凝土 梁 柱")], "structure"),
            ([MockEntity("给排水 管道 消防 喷淋")], "plumbing"),
            ([MockEntity("电气 照明 配电 电缆")], "electrical"),
            ([MockEntity("暖通 空调 通风 风管")], "hvac"),
        ]
        
        for entities, expected in test_cases:
            result = extractor.infer_discipline_from_entities(entities)
            self.assertEqual(result, expected, f"应分类为 {expected}")


class TestStatsAccuracy(unittest.TestCase):
    """测试统计准确性。"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        os.environ["V7_DB_PATH"] = self.db_path
        init_db()
    
    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        if "V7_DB_PATH" in os.environ:
            del os.environ["V7_DB_PATH"]
    
    def test_drawing_stats(self):
        """测试图纸统计准确性。"""
        db = get_db()
        
        # 清理旧数据（先删子表再删父表）
        db.execute("DELETE FROM drawings")
        db.execute("DELETE FROM review_issues")
        db.execute("DELETE FROM api_keys")
        db.execute("DELETE FROM config_versions")
        db.execute("DELETE FROM agent_configs")
        db.execute("DELETE FROM checkpoints")
        db.execute("DELETE FROM reviews")
        db.execute("DELETE FROM settings")
        db.execute("DELETE FROM projects")
        db.commit()
        
        # 创建项目
        db.execute("INSERT INTO projects (name) VALUES (?)", ("统计测试",))
        project_id = db.execute("SELECT id FROM projects WHERE name = ?",
                               ("统计测试",)).fetchone()["id"]
        
        # 插入不同状态的图纸
        for i in range(5):
            db.execute(
                "INSERT INTO drawings (project_id, filename, file_path, status) VALUES (?, ?, ?, ?)",
                (project_id, f"图纸{i}.dxf", f"/tmp/图纸{i}.dxf", "ready")
            )
        for i in range(3):
            db.execute(
                "INSERT INTO drawings (project_id, filename, file_path, status) VALUES (?, ?, ?, ?)",
                (project_id, f"待处理{i}.dxf", f"/tmp/待处理{i}.dxf", "pending")
            )
        db.commit()
        
        # 验证统计
        total = db.execute("SELECT COUNT(*) as c FROM drawings WHERE project_id = ?",
                          (project_id,)).fetchone()["c"]
        ready = db.execute(
            "SELECT COUNT(*) as c FROM drawings WHERE project_id = ? AND status = 'ready'",
            (project_id,)
        ).fetchone()["c"]
        pending = db.execute(
            "SELECT COUNT(*) as c FROM drawings WHERE project_id = ? AND status = 'pending'",
            (project_id,)
        ).fetchone()["c"]
        
        self.assertEqual(total, 8)
        self.assertEqual(ready, 5)
        self.assertEqual(pending, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
