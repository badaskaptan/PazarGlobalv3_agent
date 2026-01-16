"""
Debug endpoints for database inspection
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.clients.supabase import get_supabase

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/listings-count")
async def get_listings_count() -> dict[str, Any]:
    """Get count of listings by status"""
    supabase = get_supabase()
    
    try:
        # Count all listings
        all_result = supabase.table("listings").select("*").execute()
        total = len(all_result.data) if all_result.data else 0
        
        # Count active listings
        active_result = supabase.table("listings").select("*").eq("status", "active").execute()
        active = len(active_result.data) if active_result.data else 0
        
        # Get sample listings
        sample_result = supabase.table("listings").select("id,title,status,created_at").order("created_at", desc=True).limit(5).execute()
        samples = sample_result.data or []
        
        return {
            "success": True,
            "total_listings": total,
            "active_listings": active,
            "sample_listings": samples
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/search-test")
async def test_search(query: str = "samsung") -> dict[str, Any]:
    """Test search with a query"""
    from app.services.search import search_listings
    
    supabase = get_supabase()
    
    try:
        # Test search
        results = search_listings(supabase, query, limit=10)
        
        # Also check what statuses exist in DB
        all_statuses = supabase.table("listings").select("status").execute()
        status_list: list[str] = []
        if all_statuses.data:
            for r in all_statuses.data:
                if isinstance(r, dict) and "status" in r:
                    val = r["status"]
                    if isinstance(val, str):
                        status_list.append(val)
        status_list = list(set(status_list))
        
        return {
            "success": True,
            "query": query,
            "count": len(results),
            "results": results,
            "available_statuses": status_list
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
