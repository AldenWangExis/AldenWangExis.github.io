#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号文章解析器
从API获取文章数据并转换为Markdown格式
"""

import requests
import json
import re
from datetime import datetime
from bs4 import BeautifulSoup
from pathlib import Path


class WeChatArticleParser:
    """微信文章解析器"""
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://www.dajiala.com/fbmain/monitor/v3/article_detail"
    
    def fetch_article(self, article_url):
        """
        从API获取文章数据
        
        Args:
            article_url: 微信文章URL
            
        Returns:
            dict: 文章数据
        """
        params = {
            'url': article_url,
            'key': self.api_key,
            'mode': '2',
            'verifycode': ''
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data.get('code') == 0:
                return data
            else:
                print(f"API返回错误: {data.get('msg', '未知错误')}")
                return None
        except Exception as e:
            print(f"请求失败: {e}")
            return None

    def parse_html_content(self, html_content):
        """
        解析HTML内容，提取文本和图片
        
        Args:
            html_content: HTML格式的文章内容
            
        Returns:
            str: Markdown格式的内容
        """
        if not html_content:
            return ""
        
        soup = BeautifulSoup(html_content, 'html.parser')
        markdown_parts = []
        
        # 遍历所有元素
        for element in soup.descendants:
            # 跳过NavigableString的父元素，直接处理文本
            if element.name == 'img':
                # 提取图片URL
                img_url = element.get('data-src') or element.get('src', '')
                if img_url:
                    markdown_parts.append(f"\n![图片]({img_url})\n")
            
            elif element.name in ['p', 'section']:
                # 提取段落文本
                text = element.get_text(strip=True)
                if text and text not in [''.join(markdown_parts)]:
                    # 避免重复添加
                    if not any(text in part for part in markdown_parts[-3:] if part):
                        markdown_parts.append(f"\n{text}\n")
        
        # 清理和合并内容
        content = ''.join(markdown_parts)
        # 移除多余的空行
        content = re.sub(r'\n{3,}', '\n\n', content)
        return content.strip()
    
    def create_markdown(self, article_data):
        """
        创建Markdown文件
        
        Args:
            article_data: 文章数据字典
            
        Returns:
            tuple: (文件名, markdown内容)
        """
        # 提取元数据
        title = article_data.get('title', '无标题')
        create_time = article_data.get('create_time', '')
        desc = article_data.get('desc', '')
        author = article_data.get('author', '')
        content_html = article_data.get('content_multi_text', '')
        
        # 解析创建时间
        try:
            dt = datetime.strptime(create_time, '%Y-%m-%d %H:%M:%S')
            date_str = dt.strftime('%Y-%m-%d')
        except:
            date_str = datetime.now().strftime('%Y-%m-%d')
        
        # 清理标题用于文件名
        safe_title = re.sub(r'[\\/:*?"<>|]', '-', title)
        filename = f"{date_str}-{safe_title}.md"
        
        # 解析HTML内容
        content_md = self.parse_html_content(content_html)
        
        # 构建Markdown内容
        markdown_content = f"""---
title: {title}
date: {create_time}
author: {author}
description: {desc}
---

# {title}

> {desc}

{content_md}
"""
        
        return filename, markdown_content

    def save_markdown(self, filename, content, output_dir='_posts'):
        """
        保存Markdown文件
        
        Args:
            filename: 文件名
            content: Markdown内容
            output_dir: 输出目录
        """
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        file_path = output_path / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✓ 已保存: {file_path}")
        return file_path
    
    def process_article(self, article_url, output_dir='_posts'):
        """
        处理单篇文章：获取、解析、保存
        
        Args:
            article_url: 文章URL
            output_dir: 输出目录
            
        Returns:
            Path: 保存的文件路径
        """
        print(f"\n处理文章: {article_url}")
        
        # 获取文章数据
        article_data = self.fetch_article(article_url)
        if not article_data:
            print("✗ 获取文章失败")
            return None
        
        # 创建Markdown
        filename, content = self.create_markdown(article_data)
        
        # 保存文件
        return self.save_markdown(filename, content, output_dir)


def main():
    """主函数"""
    # API密钥
    API_KEY = "JZL77671d3fca9e4f88"
    
    # 目标URL列表
    article_urls = [
        "https://mp.weixin.qq.com/s/dEx52g9ebmeMAcY9yZUZmA",
        "https://mp.weixin.qq.com/s/rdFDnrHfbi5BOZrkhO80cQ",
        "https://mp.weixin.qq.com/s/tuf2F3xeZXwwTGBb-qy7Rg"
    ]
    
    # 创建解析器
    parser = WeChatArticleParser(API_KEY)
    
    # 处理所有文章
    print("=" * 60)
    print("开始处理微信文章")
    print("=" * 60)
    
    success_count = 0
    for url in article_urls:
        result = parser.process_article(url)
        if result:
            success_count += 1
    
    print("\n" + "=" * 60)
    print(f"处理完成: 成功 {success_count}/{len(article_urls)} 篇")
    print("=" * 60)


if __name__ == "__main__":
    main()
