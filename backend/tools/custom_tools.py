"""
Custom Tools - Your project-specific tools.

Add your own Python tools here and register them in claude_client.py
"""

from typing import Dict, Any, Callable
from .provider_base import ToolContext
from .providers.python_provider import PythonProvider


# ============================================================================
# Tool Registry - Automatically populated during registration
# ============================================================================

TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {}


def _register_tool(
    provider: PythonProvider,
    category: str,
    name: str,
    function: Callable,
    description: str,
    input_schema: Dict[str, Any],
    capabilities: list[str] = None,
    example_use_case: str = None
) -> None:
    """
    Register a tool with the provider and add it to the tool registry.

    This helper function registers the tool with the Python provider AND
    automatically populates the TOOL_REGISTRY for search_custom_tools().

    Args:
        provider: PythonProvider instance
        category: Tool category (e.g., youtube, arxiv, pdf, web, github, meta)
        name: Tool name (will be prefixed with category__)
        function: The async function to execute
        description: Tool description
        input_schema: JSON schema for input validation
        capabilities: List of capability keywords for search (optional)
        example_use_case: Example usage scenario (optional)
    """
    # Register with provider
    provider.register_function(
        category=category,
        name=name,
        function=function,
        description=description,
        input_schema=input_schema
    )

    # Build full tool name
    full_name = f"python__{category}__{name}"

    # Extract input parameter names from schema
    input_params = list(input_schema.get("properties", {}).keys())

    # Auto-generate capabilities from description if not provided
    if capabilities is None:
        capabilities = [
            category,
            name.replace("_", " "),
            *description.lower().split()
        ]

    # Add to registry
    TOOL_REGISTRY[full_name] = {
        "name": function.__name__,
        "category": category,
        "full_name": full_name,
        "description": description,
        "capabilities": capabilities,
        "input_params": input_params,
        "example_use_case": example_use_case or f"Use {description.lower()}"
    }

    print(f"✓ Registered: {full_name}")


# ============================================================================
# arXiv Search
# ============================================================================

async def search_arxiv(args: Dict[str, Any], context: ToolContext) -> Any:
    """
    Search for papers on arXiv.

    Args:
        args: {
            "query": str (search query),
            "max_results": int (maximum results, default: 10),
            "sort_by": str (relevance, lastUpdatedDate, submittedDate)
        }
        context: Tool execution context

    Returns:
        {
            "success": bool,
            "results": list[dict],
            "count": int,
            "error": str (if failed)
        }
    """
    try:
        import arxiv

        query = args.get("query", "")
        max_results = args.get("max_results", 10)
        sort_by_str = args.get("sort_by", "relevance")

        # Map sort_by string to arxiv.SortCriterion
        sort_map = {
            "relevance": arxiv.SortCriterion.Relevance,
            "lastUpdatedDate": arxiv.SortCriterion.LastUpdatedDate,
            "submittedDate": arxiv.SortCriterion.SubmittedDate
        }
        sort_by = sort_map.get(sort_by_str, arxiv.SortCriterion.Relevance)

        # Search papers
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=sort_by
        )

        results = []
        for paper in search.results():
            results.append({
                "arxiv_id": paper.entry_id.split("/")[-1],
                "title": paper.title,
                "authors": [author.name for author in paper.authors],
                "abstract": paper.summary,
                "pdf_url": paper.pdf_url,
                "published": paper.published.isoformat() if paper.published else None,
                "updated": paper.updated.isoformat() if paper.updated else None,
                "categories": paper.categories
            })

        return {
            "success": True,
            "results": results,
            "count": len(results),
            "query": query
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# PDF Table Extraction
# ============================================================================

async def extract_pdf_tables(args: Dict[str, Any], context: ToolContext) -> Any:
    """
    Extract tables from PDF file using pdfplumber.

    Args:
        args: {
            "pdf_path": str (path to PDF file),
            "page_range": str (optional, e.g., "1-5" or "all")
        }
        context: Tool execution context

    Returns:
        {
            "success": bool,
            "tables": list[dict],
            "count": int,
            "error": str (if failed)
        }
    """
    try:
        import pdfplumber
        import os

        pdf_path = args.get("pdf_path", "")
        page_range = args.get("page_range", "all")

        if not os.path.exists(pdf_path):
            return {
                "success": False,
                "error": f"PDF file not found: {pdf_path}"
            }

        tables = []

        with pdfplumber.open(pdf_path) as pdf:
            # Determine page range
            if page_range == "all":
                pages = pdf.pages
            else:
                start, end = map(int, page_range.split("-"))
                pages = pdf.pages[start-1:end]

            # Extract tables from each page
            for page_num, page in enumerate(pages, start=1):
                page_tables = page.extract_tables()
                for table_num, table in enumerate(page_tables, start=1):
                    tables.append({
                        "page": page_num,
                        "table_number": table_num,
                        "rows": len(table),
                        "columns": len(table[0]) if table else 0,
                        "data": table
                    })

        return {
            "success": True,
            "tables": tables,
            "count": len(tables),
            "pages_scanned": len(pages)
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# PDF Figure Extraction
# ============================================================================

async def extract_pdf_figures(args: Dict[str, Any], context: ToolContext) -> Any:
    """
    Extract images/figures from PDF file using PyMuPDF.

    Args:
        args: {
            "pdf_path": str (path to PDF file),
            "save_dir": str (directory to save images),
            "page_range": str (optional, e.g., "1-5" or "all")
        }
        context: Tool execution context

    Returns:
        {
            "success": bool,
            "images": list[dict],
            "count": int,
            "error": str (if failed)
        }
    """
    try:
        import fitz  # PyMuPDF
        import os

        pdf_path = args.get("pdf_path", "")
        save_dir = args.get("save_dir", context.working_directory or ".")
        page_range = args.get("page_range", "all")

        if not os.path.exists(pdf_path):
            return {
                "success": False,
                "error": f"PDF file not found: {pdf_path}"
            }

        # Create save directory if it doesn't exist
        os.makedirs(save_dir, exist_ok=True)

        # Open PDF
        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        # Determine page range
        if page_range == "all":
            pages = range(total_pages)
        else:
            start, end = map(int, page_range.split("-"))
            pages = range(start - 1, end)

        images = []
        image_count = 0

        # Extract images from each page
        for page_num in pages:
            if page_num < total_pages:
                page = doc[page_num]
                image_list = page.get_images()

                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]

                    # Save image
                    image_filename = f"page{page_num + 1}_img{img_index + 1}.{image_ext}"
                    image_path = os.path.join(save_dir, image_filename)

                    with open(image_path, "wb") as img_file:
                        img_file.write(image_bytes)

                    images.append({
                        "page": page_num + 1,
                        "image_number": img_index + 1,
                        "filename": image_filename,
                        "path": image_path,
                        "format": image_ext,
                        "size": len(image_bytes)
                    })
                    image_count += 1

        doc.close()

        return {
            "success": True,
            "images": images,
            "count": image_count,
            "save_dir": save_dir
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# GitHub Repository Search
# ============================================================================

async def search_github_repos(args: Dict[str, Any], context: ToolContext) -> Any:
    """
    Search GitHub repositories with metadata.

    Args:
        args: {
            "query": str (search query),
            "sort": str (stars, forks, updated, help-wanted-issues),
            "max_results": int (maximum results, default: 10)
        }
        context: Tool execution context

    Returns:
        {
            "success": bool,
            "repositories": list[dict],
            "count": int,
            "error": str (if failed)
        }
    """
    try:
        import requests

        query = args.get("query", "")
        sort = args.get("sort", "stars")
        max_results = args.get("max_results", 10)

        # GitHub API endpoint
        url = "https://api.github.com/search/repositories"
        params = {
            "q": query,
            "sort": sort,
            "order": "desc",
            "per_page": min(max_results, 100)  # GitHub API limit
        }

        # Make request
        headers = {"Accept": "application/vnd.github.v3+json"}
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()

        data = response.json()

        repositories = []
        for repo in data.get("items", [])[:max_results]:
            repositories.append({
                "name": repo["name"],
                "full_name": repo["full_name"],
                "owner": repo["owner"]["login"],
                "description": repo.get("description", ""),
                "url": repo["html_url"],
                "stars": repo["stargazers_count"],
                "forks": repo["forks_count"],
                "watchers": repo["watchers_count"],
                "open_issues": repo["open_issues_count"],
                "license": repo["license"]["name"] if repo.get("license") else None,
                "language": repo.get("language"),
                "created_at": repo["created_at"],
                "updated_at": repo["updated_at"],
                "topics": repo.get("topics", [])
            })

        return {
            "success": True,
            "repositories": repositories,
            "count": len(repositories),
            "total_count": data.get("total_count", 0),
            "query": query
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# Registration Function
# ============================================================================

def register_custom_tools(provider: PythonProvider) -> None:
    """
    Register all custom tools with the Python provider.

    Call this function from claude_client.py during provider initialization.

    Args:
        provider: PythonProvider instance
    """

    # Register download_youtube_thumbnail
    _register_tool(
        provider=provider,
        category="youtube",
        name="download_thumbnail",
        function=download_youtube_thumbnail,
        description="Download YouTube video thumbnail image",
        input_schema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "YouTube video URL"
                },
                "quality": {
                    "type": "string",
                    "enum": ["maxresdefault", "sddefault", "hqdefault", "mqdefault", "default"],
                    "description": "Thumbnail quality",
                    "default": "maxresdefault"
                }
            },
            "required": ["url"]
        },
        capabilities=["download", "thumbnail", "youtube", "video", "image", "media"],
        example_use_case="Download thumbnails for video analysis or archiving"
    )

    # Register download_youtube_transcript
    _register_tool(
        provider=provider,
        category="youtube",
        name="download_transcript",
        function=download_youtube_transcript,
        description="Download YouTube video transcript/captions",
        input_schema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "YouTube video URL"
                },
                "language": {
                    "type": "string",
                    "description": "Language code (e.g., en, es, fr)",
                    "default": "en"
                }
            },
            "required": ["url"]
        },
        capabilities=["download", "transcript", "captions", "youtube", "video", "subtitles", "text"],
        example_use_case="Extract video transcripts for content analysis or translation"
    )

    # Register download_arxiv_paper
    _register_tool(
        provider=provider,
        category="arxiv",
        name="download_paper",
        function=download_arxiv_paper,
        description="Download arXiv paper PDF with metadata",
        input_schema={
            "type": "object",
            "properties": {
                "arxiv_id": {
                    "type": "string",
                    "description": "arXiv paper ID (e.g., 2301.12345 or arXiv:2301.12345)"
                },
                "save_path": {
                    "type": "string",
                    "description": "Directory to save PDF (optional)"
                }
            },
            "required": ["arxiv_id"]
        },
        capabilities=["download", "arxiv", "paper", "pdf", "research", "academic"],
        example_use_case="Download research papers for literature review or analysis"
    )

    # Register extract_text_from_pdf
    _register_tool(
        provider=provider,
        category="pdf",
        name="extract_text",
        function=extract_text_from_pdf,
        description="Extract text from PDF file using PyMuPDF",
        input_schema={
            "type": "object",
            "properties": {
                "pdf_path": {
                    "type": "string",
                    "description": "Path to PDF file"
                },
                "page_range": {
                    "type": "string",
                    "description": "Page range to extract (e.g., '1-5' or 'all')",
                    "default": "all"
                }
            },
            "required": ["pdf_path"]
        },
        capabilities=["extract", "pdf", "text", "document", "parse"],
        example_use_case="Extract text content from PDF documents for analysis"
    )

    # Register crawl_website
    _register_tool(
        provider=provider,
        category="web",
        name="crawl",
        function=crawl_website,
        description="Crawl website and extract content using Crawl4AI",
        input_schema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to crawl"
                },
                "output_format": {
                    "type": "string",
                    "enum": ["markdown", "html", "text"],
                    "description": "Output format",
                    "default": "markdown"
                },
                "deep_crawl": {
                    "type": "boolean",
                    "description": "Whether to deep crawl",
                    "default": False
                },
                "max_pages": {
                    "type": "integer",
                    "description": "Maximum pages for deep crawl",
                    "default": 1
                },
                "extract_question": {
                    "type": "string",
                    "description": "Optional LLM extraction question"
                }
            },
            "required": ["url"]
        },
        capabilities=["crawl", "web", "scrape", "html", "markdown", "content", "extract"],
        example_use_case="Extract content from websites for analysis or archiving"
    )

    # Register create_pdf
    _register_tool(
        provider=provider,
        category="pdf",
        name="create",
        function=create_pdf,
        description="Create a PDF document from text content",
        input_schema={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Text content for PDF"
                },
                "filename": {
                    "type": "string",
                    "description": "Output filename",
                    "default": "output.pdf"
                },
                "title": {
                    "type": "string",
                    "description": "PDF title"
                },
                "author": {
                    "type": "string",
                    "description": "PDF author"
                },
                "save_path": {
                    "type": "string",
                    "description": "Directory to save PDF"
                }
            },
            "required": ["content"]
        },
        capabilities=["create", "pdf", "generate", "document", "text"],
        example_use_case="Generate PDF reports or documents from text content"
    )

    # Register arxiv_search
    _register_tool(
        provider=provider,
        category="arxiv",
        name="search",
        function=search_arxiv,
        description="Search for papers on arXiv by query",
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'attention mechanism', 'au:Vaswani')"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 10
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["relevance", "lastUpdatedDate", "submittedDate"],
                    "description": "Sort order for results",
                    "default": "relevance"
                }
            },
            "required": ["query"]
        },
        capabilities=["search", "arxiv", "papers", "research", "academic", "query"],
        example_use_case="Find relevant research papers on a specific topic"
    )

    # Register extract_pdf_tables
    _register_tool(
        provider=provider,
        category="pdf",
        name="extract_tables",
        function=extract_pdf_tables,
        description="Extract tables from PDF file",
        input_schema={
            "type": "object",
            "properties": {
                "pdf_path": {
                    "type": "string",
                    "description": "Path to PDF file"
                },
                "page_range": {
                    "type": "string",
                    "description": "Page range to extract (e.g., '1-5' or 'all')",
                    "default": "all"
                }
            },
            "required": ["pdf_path"]
        },
        capabilities=["extract", "pdf", "tables", "data", "structured"],
        example_use_case="Extract tabular data from PDF reports or documents"
    )

    # Register extract_pdf_figures
    _register_tool(
        provider=provider,
        category="pdf",
        name="extract_figures",
        function=extract_pdf_figures,
        description="Extract images/figures from PDF file",
        input_schema={
            "type": "object",
            "properties": {
                "pdf_path": {
                    "type": "string",
                    "description": "Path to PDF file"
                },
                "save_dir": {
                    "type": "string",
                    "description": "Directory to save extracted images"
                },
                "page_range": {
                    "type": "string",
                    "description": "Page range to extract (e.g., '1-5' or 'all')",
                    "default": "all"
                }
            },
            "required": ["pdf_path"]
        },
        capabilities=["extract", "pdf", "images", "figures", "graphics"],
        example_use_case="Extract charts, diagrams, or images from PDF documents"
    )

    # Register search_github_repos
    _register_tool(
        provider=provider,
        category="github",
        name="search_repos",
        function=search_github_repos,
        description="Search GitHub repositories with metadata (stars, license, etc.)",
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'machine learning', 'language:python')"
                },
                "sort": {
                    "type": "string",
                    "enum": ["stars", "forks", "updated", "help-wanted-issues"],
                    "description": "Sort order",
                    "default": "stars"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 10
                }
            },
            "required": ["query"]
        },
        capabilities=["search", "github", "repositories", "code", "open-source", "stars", "license"],
        example_use_case="Find relevant open-source projects or libraries on GitHub"
    )

    print(f"\n✓ Total custom tools registered: {len(TOOL_REGISTRY)}")


# ============================================================================
# YouTube Tools
# ============================================================================

async def download_youtube_thumbnail(args: Dict[str, Any], context: ToolContext) -> Any:
    """
    Download YouTube video thumbnail.

    Args:
        args: {
            "url": str (YouTube video URL),
            "quality": str (maxresdefault, sddefault, hqdefault, mqdefault, default)
        }
        context: Tool execution context

    Returns:
        {
            "success": bool,
            "thumbnail_url": str,
            "video_id": str,
            "error": str (if failed)
        }
    """
    try:
        from urllib.parse import urlparse, parse_qs
        import re

        url = args.get("url", "")
        quality = args.get("quality", "maxresdefault")

        # Extract video ID from URL
        video_id = None

        # Handle different YouTube URL formats
        if "youtu.be/" in url:
            video_id = url.split("youtu.be/")[1].split("?")[0]
        elif "youtube.com/watch" in url:
            parsed = urlparse(url)
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif "youtube.com/embed/" in url:
            video_id = url.split("youtube.com/embed/")[1].split("?")[0]

        if not video_id:
            return {
                "success": False,
                "error": "Could not extract video ID from URL"
            }

        # Construct thumbnail URL
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/{quality}.jpg"

        return {
            "success": True,
            "thumbnail_url": thumbnail_url,
            "video_id": video_id,
            "quality": quality
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def download_youtube_transcript(args: Dict[str, Any], context: ToolContext) -> Any:
    """
    Download YouTube video transcript/captions.

    Args:
        args: {
            "url": str (YouTube video URL),
            "language": str (language code, default: en)
        }
        context: Tool execution context

    Returns:
        {
            "success": bool,
            "transcript": str,
            "video_id": str,
            "language": str,
            "error": str (if failed)
        }
    """
    try:
        import youtube_transcript_api
        from urllib.parse import urlparse, parse_qs

        url = args.get("url", "")
        language = args.get("language", "en")

        # Extract video ID
        video_id = None
        if "youtu.be/" in url:
            video_id = url.split("youtu.be/")[1].split("?")[0]
        elif "youtube.com/watch" in url:
            parsed = urlparse(url)
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif "youtube.com/embed/" in url:
            video_id = url.split("youtube.com/embed/")[1].split("?")[0]

        if not video_id:
            return {
                "success": False,
                "error": "Could not extract video ID from URL"
            }

        # Get transcript using the fetch method
        api = youtube_transcript_api.YouTubeTranscriptApi()
        transcript_list = api.fetch(video_id, [language])

        # Combine all text segments
        transcript_text = "\n".join([item.text for item in transcript_list])

        return {
            "success": True,
            "transcript": transcript_text,
            "video_id": video_id,
            "language": language,
            "segments": len(transcript_list)
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# arXiv Paper Download
# ============================================================================

async def download_arxiv_paper(args: Dict[str, Any], context: ToolContext) -> Any:
    """
    Download arXiv paper PDF.

    Args:
        args: {
            "arxiv_id": str (arXiv ID, e.g., 2301.12345 or arXiv:2301.12345),
            "save_path": str (optional, path to save PDF)
        }
        context: Tool execution context

    Returns:
        {
            "success": bool,
            "title": str,
            "authors": list[str],
            "abstract": str,
            "pdf_url": str,
            "saved_to": str,
            "error": str (if failed)
        }
    """
    try:
        import arxiv
        import os

        arxiv_id = args.get("arxiv_id", "").replace("arXiv:", "").strip()
        save_path = args.get("save_path", context.working_directory or ".")

        # Search for the paper
        search = arxiv.Search(id_list=[arxiv_id])
        paper = next(search.results())

        # Download PDF
        pdf_filename = f"{arxiv_id.replace('/', '_')}.pdf"
        pdf_path = os.path.join(save_path, pdf_filename)
        paper.download_pdf(filename=pdf_path)

        return {
            "success": True,
            "title": paper.title,
            "authors": [author.name for author in paper.authors],
            "abstract": paper.summary,
            "pdf_url": paper.pdf_url,
            "saved_to": pdf_path,
            "arxiv_id": arxiv_id
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# PDF Text Extraction (PyMuPDF)
# ============================================================================

async def extract_text_from_pdf(args: Dict[str, Any], context: ToolContext) -> Any:
    """
    Extract text from PDF file using PyMuPDF.

    Args:
        args: {
            "pdf_path": str (path to PDF file),
            "page_range": str (optional, e.g., "1-5" or "all")
        }
        context: Tool execution context

    Returns:
        {
            "success": bool,
            "text": str,
            "pages": int,
            "metadata": dict,
            "error": str (if failed)
        }
    """
    try:
        import fitz  # PyMuPDF
        import os

        pdf_path = args.get("pdf_path", "")
        page_range = args.get("page_range", "all")

        if not os.path.exists(pdf_path):
            return {
                "success": False,
                "error": f"PDF file not found: {pdf_path}"
            }

        # Open PDF
        doc = fitz.open(pdf_path)

        # Get page count and metadata before processing
        total_pages = len(doc)
        metadata = dict(doc.metadata)

        # Determine page range
        if page_range == "all":
            pages = range(total_pages)
        else:
            # Parse range like "1-5"
            start, end = map(int, page_range.split("-"))
            pages = range(start - 1, end)  # Convert to 0-indexed

        # Extract text
        text_parts = []
        for page_num in pages:
            if page_num < total_pages:
                page = doc[page_num]
                text_parts.append(page.get_text())

        full_text = "\n".join(text_parts)

        # Close document
        doc.close()

        return {
            "success": True,
            "text": full_text,
            "pages": total_pages,
            "extracted_pages": len(list(pages)),
            "metadata": metadata
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# Web Crawling (Crawl4AI)
# ============================================================================

async def crawl_website(args: Dict[str, Any], context: ToolContext) -> Any:
    """
    Crawl website and extract content using Crawl4AI.

    Args:
        args: {
            "url": str (URL to crawl),
            "output_format": str (markdown, html, text),
            "deep_crawl": bool (whether to deep crawl),
            "max_pages": int (max pages for deep crawl, default: 1),
            "extract_question": str (optional, LLM extraction question)
        }
        context: Tool execution context

    Returns:
        {
            "success": bool,
            "content": str,
            "url": str,
            "title": str,
            "error": str (if failed)
        }
    """
    try:
        from crawl4ai import AsyncWebCrawler
        import asyncio

        url = args.get("url", "")
        output_format = args.get("output_format", "markdown")
        deep_crawl = args.get("deep_crawl", False)
        max_pages = args.get("max_pages", 1)
        extract_question = args.get("extract_question")

        if not url:
            return {
                "success": False,
                "error": "URL is required"
            }

        # Create crawler and run
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)

            # Get content based on format
            if output_format == "markdown":
                content = result.markdown
            elif output_format == "html":
                content = result.html
            else:
                content = result.cleaned_html

            return {
                "success": True,
                "content": content,
                "url": url,
                "title": getattr(result, "title", ""),
                "output_format": output_format
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# PDF Maker
# ============================================================================

async def create_pdf(args: Dict[str, Any], context: ToolContext) -> Any:
    """
    Create a PDF document from text content.

    Args:
        args: {
            "content": str (text content for PDF),
            "filename": str (output filename),
            "title": str (optional, PDF title),
            "author": str (optional, PDF author),
            "save_path": str (optional, directory to save PDF)
        }
        context: Tool execution context

    Returns:
        {
            "success": bool,
            "pdf_path": str,
            "error": str (if failed)
        }
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.enums import TA_JUSTIFY
        import os

        content = args.get("content", "")
        filename = args.get("filename", "output.pdf")
        title = args.get("title", "Document")
        author = args.get("author", "")
        save_path = args.get("save_path", context.working_directory or ".")

        # Ensure filename ends with .pdf
        if not filename.endswith(".pdf"):
            filename += ".pdf"

        pdf_path = os.path.join(save_path, filename)

        # Create PDF
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        story = []

        # Get styles
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name='Justify',
            alignment=TA_JUSTIFY,
            fontSize=12,
            leading=14
        ))

        # Add title
        if title:
            title_style = styles['Heading1']
            story.append(Paragraph(title, title_style))
            story.append(Spacer(1, 0.2 * inch))

        # Add content (split by paragraphs)
        paragraphs = content.split('\n\n')
        for para in paragraphs:
            if para.strip():
                p = Paragraph(para.strip().replace('\n', '<br/>'), styles['Justify'])
                story.append(p)
                story.append(Spacer(1, 0.1 * inch))

        # Build PDF
        doc.build(story)

        return {
            "success": True,
            "pdf_path": pdf_path,
            "title": title,
            "author": author
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
