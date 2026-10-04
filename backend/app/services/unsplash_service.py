"""Unsplash图片服务"""

import requests
import socket
from typing import List, Optional
from ..config import get_settings

class UnsplashService:
    """Unsplash图片服务类"""
    
    def __init__(self):
        """初始化服务"""
        settings = get_settings()
        self.access_key = settings.unsplash_access_key
        self.base_url = "https://api.unsplash.com"
        # 默认图片列表，当Unsplash API不可用时使用
        self.default_images = {
            "故宫": "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=The%20Forbidden%20City%20in%20Beijing%20China%2C%20historic%20palace%2C%20aerial%20view%2C%20clear%20sky%2C%20tourists&image_size=landscape_16_9",
            "长城": "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=The%20Great%20Wall%20of%20China%2C%20mountainous%20landscape%2C%20sunset%2C%20historic%20structure&image_size=landscape_16_9",
            "颐和园": "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=Summer%20Palace%20in%20Beijing%2C%20traditional%20Chinese%20garden%2C%20lake%2C%20pavilions%2C%20beautiful%20landscape&image_size=landscape_16_9",
            "天坛": "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=Temple%20of%20Heaven%20in%20Beijing%2C%20traditional%20Chinese%20architecture%2C%20blue%20roof%2C%20park%20surroundings&image_size=landscape_16_9",
            "天安门": "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=Tiananmen%20Square%20in%20Beijing%2C%20gateway%2C%20flag%2C%20tourists%2C%20city%20view&image_size=landscape_16_9",
            "北京景点": "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=Beijing%20city%20skyline%2C%20modern%20and%20traditional%20architecture%2C%20beautiful%20view&image_size=landscape_16_9",
            "上海景点": "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=Shanghai%20skyline%20with%20the%20Bund%20and%20Pudong%2C%20night%20view%2C%20lights%2C%20river&image_size=landscape_16_9",
            "广州景点": "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=Canton%20Tower%20in%20Guangzhou%2C%20modern%20architecture%2C%20night%20view%2C%20city%20scape&image_size=landscape_16_9",
            "深圳景点": "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=Shenzhen%20city%20skyline%2C%20modern%20buildings%2C%20technology%20hub%2C%20daytime%20view&image_size=landscape_16_9"
        }
    
    def is_connected(self) -> bool:
        """
        检查网络连接状态
        
        Returns:
            bool: 是否连接成功
        """
        try:
            # 尝试解析Unsplash API域名
            socket.gethostbyname("api.unsplash.com")
            return True
        except socket.gaierror:
            print("❌ 网络连接失败: 无法解析Unsplash API域名")
            return False
    
    def search_photos(self, query: str, per_page: int = 5) -> List[dict]:
        """
        搜索图片
        
        Args:
            query: 搜索关键词
            per_page: 每页数量
            
        Returns:
            图片列表
        """
        try:
            # 检查网络连接
            if not self.is_connected():
                print(f"⚠️  网络连接失败，使用默认图片: {query}")
                return []
            
            url = f"{self.base_url}/search/photos"
            params = {
                "query": query,
                "per_page": per_page,
                "client_id": self.access_key
            }
            
            print(f"🔍 正在搜索Unsplash图片: {query}")
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            
            print(f"✅ Unsplash搜索成功，找到 {len(results)} 张图片")
            
            # 提取图片URL
            photos = []
            for photo in results:
                photos.append({
                    "id": photo.get("id"),
                    "url": photo.get("urls", {}).get("regular"),
                    "thumb": photo.get("urls", {}).get("thumb"),
                    "description": photo.get("description") or photo.get("alt_description"),
                    "photographer": photo.get("user", {}).get("name")
                })
            
            return photos
            
        except requests.exceptions.Timeout:
            print(f"❌ Unsplash搜索超时: {query}")
            return []
        except requests.exceptions.ConnectionError:
            print(f"❌ Unsplash连接错误: {query}")
            return []
        except requests.exceptions.HTTPError as e:
            print(f"❌ Unsplash HTTP错误: {str(e)}")
            return []
        except Exception as e:
            print(f"❌ Unsplash搜索失败: {str(e)}")
            return []
    
    def get_photo_url(self, query: str) -> Optional[str]:
        """
        获取单张图片URL

        Args:
            query: 搜索关键词

        Returns:
            图片URL
        """
        # 尝试从Unsplash获取图片
        photos = self.search_photos(query, per_page=1)
        if photos:
            return photos[0].get("url")
        
        # 如果Unsplash失败，使用默认图片
        print(f"⚠️ Unsplash失败，使用默认图片: {query}")
        
        # 尝试匹配默认图片
        for key, url in self.default_images.items():
            if key in query:
                return url
        
        # 返回通用景点图片
        return self.default_images.get("北京景点")


# 全局服务实例
_unsplash_service = None


def get_unsplash_service() -> UnsplashService:
    """获取Unsplash服务实例(单例模式)"""
    global _unsplash_service
    
    if _unsplash_service is None:
        _unsplash_service = UnsplashService()
    
    return _unsplash_service

