#!/usr/bin/env python3
"""
重复文件查找器
用于查找指定目录中的重复文件

支持 GUI 和 CLI 模式：
- GUI 模式（默认）：python main.py
- CLI 模式：python main.py --scan /path/to/directory
"""

import sys
import argparse
from pathlib import Path

from gui import main as gui_main
from logger import get_logger


class DuplicateFinderCLI:
    """命令行界面"""

    def __init__(self):
        self.log = get_logger()

    def run(self, args):
        """运行 CLI 命令"""
        if args.command == 'scan':
            return self.scan_directory(args)
        elif args.command == 'export':
            return self.export_report(args)
        else:
            self.print_help()
            return 1

    def scan_directory(self, args):
        """扫描目录查找重复文件"""
        from file_scanner import FileScanner, HashCalculator
        from duplicate_finder import DuplicateFinder

        directory = Path(args.directory)
        if not directory.exists() or not directory.is_dir():
            print(f"错误: 目录不存在: {args.directory}")
            return 1

        print(f"正在扫描目录: {directory}")

        # Parse file extensions
        extensions = None
        if args.extensions:
            extensions = set(ext.strip().lower() for ext in args.extensions.split(','))
            # Normalize extensions
            extensions = {e if e.startswith('.') else f'.{e}' for e in extensions}
            print(f"文件类型过滤: {', '.join(extensions)}")

        # Create scanner and finder
        scanner = FileScanner(extensions)
        hash_calculator = HashCalculator()
        finder = DuplicateFinder(
            scanner,
            hash_calculator,
            use_parallel=not args.no_parallel,
            cache_enabled=not args.no_cache,
            use_multi_stage=not args.no_multi_stage
        )

        # Scan for duplicates
        try:
            def scan_progress(current, total):
                if total > 0 and current % max(1, total // 20) == 0:
                    pct = int(current / total * 100)
                    print(f"  扫描进度: {pct}% ({current}/{total})")

            def hash_progress(current, total):
                if total > 0 and current % max(1, total // 20) == 0:
                    pct = int(current / total * 100)
                    print(f"  哈希进度: {pct}% ({current}/{total})")

            results = finder.find_duplicates(
                str(directory),
                scan_progress_callback=scan_progress,
                hash_progress_callback=hash_progress
            )

            # Print results
            if not results:
                print("\n未找到重复文件")
                return 0

            total_files = sum(len(g.files) for g in results)
            wasted_space = finder.get_total_wasted_space(results)

            print(f"\n扫描完成:")
            print(f"  重复文件组: {len(results)}")
            print(f"  重复文件数: {total_files}")
            print(f"  浪费空间: {self._format_size(wasted_space)}")

            # Print duplicate groups
            if args.verbose:
                print("\n重复文件详情:")
                for i, group in enumerate(results, 1):
                    print(f"\n组 #{i} (哈希: {group.hash_value[:16]}...):")
                    for j, file_info in enumerate(group.files):
                        prefix = "  " if j == 0 else "    * "
                        print(f"{prefix}{file_info.path}")
                        print(f"      大小: {self._format_size(file_info.size)}")

            # Auto delete if requested
            if args.delete:
                return self.delete_duplicates(results, args)

            return 0

        except KeyboardInterrupt:
            print("\n扫描已取消")
            return 130
        except Exception as e:
            print(f"错误: {e}")
            return 1

    def delete_duplicates(self, duplicate_groups, args):
        """删除重复文件"""
        if not args.delete:
            return 0

        # Check if send2trash is available
        try:
            from send2trash import send2trash
            use_trash = True
        except ImportError:
            use_trash = False

        total_to_delete = 0
        total_space = 0

        for group in duplicate_groups:
            # Keep first file, delete rest
            for file_info in group.files[1:]:
                total_to_delete += 1
                total_space += file_info.size

        print(f"\n将删除 {total_to_delete} 个文件，释放 {self._format_size(total_space)} 空间")

        if not args.force:
            response = input("确认删除? (yes/no): ")
            if response.lower() != 'yes':
                print("取消删除")
                return 0

        # Perform deletion
        deleted_count = 0
        failed_count = 0

        for group in duplicate_groups:
            for file_info in group.files[1:]:
                try:
                    if use_trash:
                        send2trash(file_info.path)
                    else:
                        import os
                        os.remove(file_info.path)
                    deleted_count += 1
                except Exception as e:
                    print(f"删除失败: {file_info.path} - {e}")
                    failed_count += 1

        print(f"\n删除完成:")
        print(f"  成功: {deleted_count} 个文件")
        if failed_count > 0:
            print(f"  失败: {failed_count} 个文件")
        print(f"  释放空间: {self._format_size(total_space)}")

        return 0

    def export_report(self, args):
        """导出扫描报告"""
        from file_scanner import FileScanner, HashCalculator
        from duplicate_finder import DuplicateFinder
        from export_manager import ExportManager

        # First scan the directory
        directory = Path(args.directory)
        if not directory.exists() or not directory.is_dir():
            print(f"错误: 目录不存在: {args.directory}")
            return 1

        print(f"正在扫描目录: {directory}")

        scanner = FileScanner(None)  # Scan all files
        hash_calculator = HashCalculator()
        finder = DuplicateFinder(scanner, hash_calculator)

        try:
            results = finder.find_duplicates(str(directory))
            print(f"找到 {len(results)} 组重复文件")
        except Exception as e:
            print(f"扫描错误: {e}")
            return 1

        # Export report
        output_path = args.output or f"duplicate_report_{args.format}"

        exporter = ExportManager()
        success = False

        if args.format == 'csv':
            success = exporter.export_to_csv(results, output_path, not args.minimal)
        elif args.format == 'json':
            success = exporter.export_to_json(results, output_path, not args.minimal)
        elif args.format == 'html':
            success = exporter.export_to_html(results, output_path)

        if success:
            print(f"报告已导出到: {output_path}")
            return 0
        else:
            print(f"导出失败")
            return 1

    def print_help(self):
        """打印帮助信息"""
        parser = self.create_parser()
        parser.print_help()

    @staticmethod
    def _format_size(size: int) -> str:
        """格式化文件大小"""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"

    @staticmethod
    def create_parser():
        """创建命令行解析器"""
        parser = argparse.ArgumentParser(
            description='重复文件查找器 - 查找并管理重复文件',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
示例:
  python main.py                              # 启动 GUI
  python main.py --scan ~/Pictures            # 扫描目录
  python main.py --scan ~/Documents -v        # 详细输出
  python main.py --scan ~/Downloads --delete  # 扫描并自动删除
  python main.py --export ~/Pictures -f html  # 导出 HTML 报告
            """
        )

        subparsers = parser.add_subparsers(dest='command', help='命令')

        # Scan command
        scan_parser = subparsers.add_parser('scan', help='扫描目录查找重复文件')
        scan_parser.add_argument('directory', help='要扫描的目录路径')
        scan_parser.add_argument('-e', '--extensions', help='文件扩展名过滤（逗号分隔，如: jpg,png,mp4）')
        scan_parser.add_argument('-v', '--verbose', action='store_true', help='显示详细输出')
        scan_parser.add_argument('--delete', action='store_true', help='自动删除重复文件（保留每组第一个）')
        scan_parser.add_argument('--force', action='store_true', help='跳过确认直接删除')
        scan_parser.add_argument('--no-parallel', action='store_true', help='禁用并行哈希计算')
        scan_parser.add_argument('--no-cache', action='store_true', help='禁用哈希缓存')
        scan_parser.add_argument('--no-multi-stage', action='store_true', help='禁用多阶段哈希')

        # Export command
        export_parser = subparsers.add_parser('export', help='扫描并导出报告')
        export_parser.add_argument('directory', help='要扫描的目录路径')
        export_parser.add_argument('-f', '--format', choices=['csv', 'json', 'html'],
                                   default='html', help='导出格式（默认: html）')
        export_parser.add_argument('-o', '--output', help='输出文件路径')
        export_parser.add_argument('--minimal', action='store_true', help='不包含完整元数据')

        return parser


def main():
    """主入口"""
    parser = DuplicateFinderCLI.create_parser()
    args = parser.parse_args()

    # If no command specified, launch GUI
    if args.command is None:
        gui_main()
    else:
        # Run CLI mode
        cli = DuplicateFinderCLI()
        sys.exit(cli.run(args))


if __name__ == "__main__":
    main()
