#!/usr/bin/env python3
"""
功能测试脚本

测试 ROADMAP 中实现的所有功能
"""
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def create_test_files():
    """创建测试文件"""
    test_dir = tempfile.mkdtemp(prefix="duplicate_finder_test_")
    print(f"创建测试目录: {test_dir}")

    # 创建一些子目录
    subdir1 = os.path.join(test_dir, "folder1")
    subdir2 = os.path.join(test_dir, "folder2")
    os.makedirs(subdir1)
    os.makedirs(subdir2)

    # 创建测试文件
    test_files = []

    # 创建重复文件（相同内容）
    content1 = b"Hello, World! This is a test file."
    content2 = b"Different content for testing."

    # 文件1和文件2是重复的
    with open(os.path.join(subdir1, "file1.txt"), "wb") as f:
        f.write(content1)
    test_files.append(os.path.join(subdir1, "file1.txt"))

    with open(os.path.join(subdir2, "file2.txt"), "wb") as f:
        f.write(content1)
    test_files.append(os.path.join(subdir2, "file2.txt"))

    # 文件3是不同的
    with open(os.path.join(subdir1, "file3.txt"), "wb") as f:
        f.write(content2)
    test_files.append(os.path.join(subdir1, "file3.txt"))

    # 创建空文件（应该被跳过）
    with open(os.path.join(test_dir, "empty.txt"), "wb") as f:
        pass

    return test_dir, test_files


def cleanup_test_files(test_dir):
    """清理测试文件"""
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
        print(f"清理测试目录: {test_dir}")


def test_file_scanner():
    """测试文件扫描器"""
    print("\n" + "="*50)
    print("测试 1: 文件扫描器")
    print("="*50)

    from file_scanner import FileScanner

    test_dir, files = create_test_files()

    try:
        scanner = FileScanner()
        scanned_files = scanner.scan_directory(test_dir)

        print(f"✓ 扫描完成: 找到 {len(scanned_files)} 个文件")

        # 显示扫描的文件
        for f in scanned_files:
            print(f"  - {Path(f.path).name}: {f.size} bytes")

        # 测试扩展名过滤
        scanner_txt = FileScanner({'.txt'})
        txt_files = scanner_txt.scan_directory(test_dir)
        print(f"✓ 扩展名过滤: 找到 {len(txt_files)} 个 .txt 文件")

        return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        cleanup_test_files(test_dir)


def test_hash_calculator():
    """测试哈希计算器"""
    print("\n" + "="*50)
    print("测试 2: 哈希计算器")
    print("="*50)

    from file_scanner import HashCalculator

    test_dir, files = create_test_files()

    try:
        calculator = HashCalculator()

        # 计算文件1和文件2的哈希（应该是相同的）
        hash1 = calculator.calculate_file_hash(files[0])
        hash2 = calculator.calculate_file_hash(files[1])
        hash3 = calculator.calculate_file_hash(files[2])

        print(f"文件1 哈希: {hash1[:16]}...")
        print(f"文件2 哈希: {hash2[:16]}...")
        print(f"文件3 哈希: {hash3[:16]}...")

        if hash1 == hash2:
            print("✓ 重复文件检测正确: 文件1和文件2哈希相同")
        else:
            print("✗ 错误: 文件1和文件2应该有相同的哈希")
            return False

        if hash1 != hash3:
            print("✓ 不同文件检测正确: 文件1和文件3哈希不同")
        else:
            print("✗ 错误: 文件1和文件3应该有不同的哈希")
            return False

        return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        cleanup_test_files(test_dir)


def test_duplicate_finder():
    """测试重复文件查找器"""
    print("\n" + "="*50)
    print("测试 3: 重复文件查找器")
    print("="*50)

    from file_scanner import FileScanner, HashCalculator
    from duplicate_finder import DuplicateFinder

    test_dir, files = create_test_files()

    try:
        scanner = FileScanner()
        hash_calculator = HashCalculator()
        finder = DuplicateFinder(scanner, hash_calculator, use_parallel=False, cache_enabled=False)

        results = finder.find_duplicates(test_dir)

        print(f"✓ 扫描完成: 找到 {len(results)} 组重复文件")

        for i, group in enumerate(results, 1):
            print(f"\n组 #{i}:")
            for f in group.files:
                print(f"  - {f.path}")

        # 验证结果
        if len(results) == 1:
            print("✓ 正确: 找到1组重复文件")
        else:
            print(f"✗ 错误: 应该找到1组重复文件，实际找到 {len(results)} 组")
            return False

        # 测试浪费空间计算
        wasted = finder.get_total_wasted_space(results)
        print(f"✓ 浪费空间: {wasted} bytes")

        return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        cleanup_test_files(test_dir)


def test_cache_manager():
    """测试缓存管理器"""
    print("\n" + "="*50)
    print("测试 4: 缓存管理器")
    print("="*50)

    from cache_manager import HashCache

    # 使用临时文件作为缓存
    cache_file = tempfile.mktemp(suffix=".db")

    try:
        cache = HashCache(cache_file)

        # 测试基本操作
        cache.set("test1.txt", 100, 123456.0, "abc123")
        value = cache.get("test1.txt", 100, 123456.0)

        if value == "abc123":
            print("✓ 缓存设置和读取成功")
        else:
            print(f"✗ 缓存读取失败: 期望 'abc123', 得到 '{value}'")
            return False

        # 测试批量操作
        entries = [
            {'path': 'test2.txt', 'size': 200, 'mtime': 123456.0, 'hash_value': 'def456'},
            {'path': 'test3.txt', 'size': 300, 'mtime': 123456.0, 'hash_value': 'ghi789'},
        ]
        cache.set_batch(entries)

        print("✓ 批量缓存设置成功")

        # 测试统计
        stats = cache.get_stats()
        print(f"✓ 缓存统计: {stats['total_entries']} 个条目")

        # 测试清理
        cache.clear()
        stats_after = cache.get_stats()
        if stats_after['total_entries'] == 0:
            print("✓ 缓存清理成功")
        else:
            print("✗ 缓存清理失败")
            return False

        return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        if os.path.exists(cache_file):
            os.remove(cache_file)


def test_config_manager():
    """测试配置管理器"""
    print("\n" + "="*50)
    print("测试 5: 配置管理器")
    print("="*50)

    from config_manager import ConfigManager

    # 使用临时文件作为配置
    config_file = tempfile.mktemp(suffix=".json")

    try:
        config = ConfigManager(config_file)

        # 测试基本操作
        config.set("test_key", "test_value")
        value = config.get("test_key")

        if value == "test_value":
            print("✓ 配置设置和读取成功")
        else:
            print(f"✗ 配置读取失败: 期望 'test_value', 得到 '{value}'")
            return False

        # 测试默认值
        default_value = config.get("non_existent", "default")
        if default_value == "default":
            print("✓ 默认值处理正确")
        else:
            print("✗ 默认值处理失败")
            return False

        # 测试保存和加载
        result = config.save()
        if not result:
            print("✗ 配置保存失败")
            return False

        config2 = ConfigManager(config_file)
        loaded_value = config2.get("test_key")

        if loaded_value == "test_value":
            print("✓ 配置保存和加载成功")
        else:
            print("✗ 配置保存和加载失败")
            return False

        return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        if os.path.exists(config_file):
            os.remove(config_file)


def test_export_manager():
    """测试导出管理器"""
    print("\n" + "="*50)
    print("测试 6: 导出管理器")
    print("="*50)

    from file_scanner import FileScanner, HashCalculator
    from duplicate_finder import DuplicateFinder
    from export_manager import ExportManager

    test_dir, files = create_test_files()
    output_dir = tempfile.mkdtemp(prefix="export_test_")

    try:
        # 先扫描重复文件
        scanner = FileScanner()
        hash_calculator = HashCalculator()
        finder = DuplicateFinder(scanner, hash_calculator, use_parallel=False, cache_enabled=False)
        results = finder.find_duplicates(test_dir)

        # 测试CSV导出
        exporter = ExportManager()
        csv_file = os.path.join(output_dir, "test.csv")
        if exporter.export_to_csv(results, csv_file, include_metadata=True):
            print("✓ CSV 导出成功")
        else:
            print("✗ CSV 导出失败")
            return False

        # 测试JSON导出
        json_file = os.path.join(output_dir, "test.json")
        if exporter.export_to_json(results, json_file, include_metadata=True):
            print("✓ JSON 导出成功")
        else:
            print("✗ JSON 导出失败")
            return False

        # 测试HTML导出
        html_file = os.path.join(output_dir, "test.html")
        if exporter.export_to_html(results, html_file):
            print("✓ HTML 导出成功")
        else:
            print("✗ HTML 导出失败")
            return False

        # 验证文件存在
        for fmt, path in [("CSV", csv_file), ("JSON", json_file), ("HTML", html_file)]:
            if os.path.exists(path):
                size = os.path.getsize(path)
                print(f"  {fmt} 文件: {size} bytes")
            else:
                print(f"✗ {fmt} 文件不存在")
                return False

        return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        cleanup_test_files(test_dir)
        shutil.rmtree(output_dir)


def test_cli_help():
    """测试 CLI 帮助"""
    print("\n" + "="*50)
    print("测试 7: CLI 帮助")
    print("="*50)

    try:
        from main import DuplicateFinderCLI

        parser = DuplicateFinderCLI.create_parser()

        # 测试 scan 命令解析
        args = parser.parse_args(['scan', '/tmp/test'])
        if args.command == 'scan' and args.directory == '/tmp/test':
            print("✓ scan 命令解析正确")
        else:
            print("✗ scan 命令解析失败")
            return False

        # 测试 export 命令解析
        args = parser.parse_args(['export', '/tmp/test', '-f', 'json'])
        if args.command == 'export' and args.format == 'json':
            print("✓ export 命令解析正确")
        else:
            print("✗ export 命令解析失败")
            return False

        # 测试 verbose 选项
        args = parser.parse_args(['scan', '/tmp/test', '-v'])
        if args.verbose:
            print("✓ verbose 选项解析正确")
        else:
            print("✗ verbose 选项解析失败")
            return False

        # 测试 delete 选项
        args = parser.parse_args(['scan', '/tmp/test', '--delete'])
        if args.delete:
            print("✓ delete 选项解析正确")
        else:
            print("✗ delete 选项解析失败")
            return False

        print("✓ CLI 参数解析全部正确")
        return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_logger():
    """测试日志系统"""
    print("\n" + "="*50)
    print("测试 8: 日志系统")
    print("="*50)

    from logger import get_logger

    try:
        log = get_logger()

        # 测试不同级别的日志
        log.info("测试 info 日志")
        log.warning("测试 warning 日志")
        log.error("测试 error 日志")

        print("✓ 日志记录成功")

        return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_permission_checking():
    """测试权限检查"""
    print("\n" + "="*50)
    print("测试 9: 权限检查")
    print("="*50)

    from file_scanner import FileScanner

    test_dir, files = create_test_files()

    try:
        scanner = FileScanner()

        # 测试正常目录
        errors = scanner.check_permissions(test_dir)
        print(f"✓ 权限检查完成: 发现 {len(errors)} 个错误")

        # 测试权限摘要
        error_count, summary = scanner.get_permission_summary()
        print(f"✓ 权限摘要: {summary}")

        return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        cleanup_test_files(test_dir)


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("开始功能测试")
    print("="*60)

    tests = [
        ("文件扫描器", test_file_scanner),
        ("哈希计算器", test_hash_calculator),
        ("重复文件查找器", test_duplicate_finder),
        ("缓存管理器", test_cache_manager),
        ("配置管理器", test_config_manager),
        ("导出管理器", test_export_manager),
        ("CLI 帮助", test_cli_help),
        ("日志系统", test_logger),
        ("权限检查", test_permission_checking),
    ]

    results = []

    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} 测试异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # 打印测试摘要
    print("\n" + "="*60)
    print("测试摘要")
    print("="*60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status} - {name}")

    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
