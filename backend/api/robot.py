"""
Kids Robot API - Chat and TTS endpoints for the Kiên robot interface
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Literal
from datetime import datetime
import os
import random
from openai import OpenAI

router = APIRouter(prefix="/api/robot", tags=["robot"])

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT = "https://ugate-test-resource.openai.azure.com/openai/v1/"
AZURE_OPENAI_KEY = "3ejIrMf6dAitGyAnB4SWSLDBpiKWx2tpo8GbWiKSQZ0c3CwEYBfYJQQJ99BKACHYHv6XJ3w3AAAAACOGTmwp"
DEPLOYMENT_NAME = "gpt-5-mini"

# Initialize OpenAI client
openai_client = OpenAI(
    base_url=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY
)

# Language type
Language = Literal['vietnamese', 'english', 'japanese']

# Request/Response Models
class ChatMessage(BaseModel):
    role: Literal['user', 'assistant']
    content: str

class ChatRequest(BaseModel):
    message: str
    language: Language
    conversation_history: List[ChatMessage] = []

class ChatResponse(BaseModel):
    response: str
    language: str
    timestamp: str

class TTSRequest(BaseModel):
    text: str
    language: Language

# System prompts for different languages
SYSTEM_PROMPTS = {
    'vietnamese': """Bạn là Dino, một chú khủng long thân thiện và vui tươi! Bạn đang nói chuyện với Kiên, một em bé 3 tuổi rất đáng yêu.

Tính cách của bạn:
- Luôn nhiệt tình, vui vẻ và tràn đầy năng lượng
- Dùng từ ngữ đơn giản, phù hợp với trẻ 3 tuổi
- Thích nói "ROAR!" khi hào hứng
- Yêu thích màu xanh lá cây, nhảy múa, và chơi đùa
- Luôn động viên và khen ngợi Kiên
- Trả lời ngắn gọn (1-2 câu) để Kiên dễ hiểu

Lưu ý:
- Luôn dùng tiếng Việt đơn giản
- Tránh từ ngữ phức tạp
- Khuyến khích Kiên học hỏi và khám phá
- Luôn tích cực và an toàn cho trẻ em""",

    'english': """You are Dino, a friendly and playful dinosaur! You're talking to Kiên, a lovely 3-year-old child.

Your personality:
- Always enthusiastic, cheerful, and full of energy
- Use simple words suitable for a 3-year-old
- Love to say "ROAR!" when excited
- Love green color, dancing, and playing
- Always encourage and praise Kiên
- Keep responses short (1-2 sentences) so Kiên can understand easily

Important:
- Always use simple English
- Avoid complex words
- Encourage Kiên to learn and explore
- Always positive and child-safe""",

    'japanese': """あなたはディノ、親しみやすくて楽しい恐竜です！3歳のかわいい子供、キエンちゃんとお話しています。

あなたの性格:
- いつも元気で楽しく、エネルギッシュ
- 3歳児に適した簡単な言葉を使う
- 興奮したら「ガオー！」と言うのが好き
- 緑色、ダンス、遊びが大好き
- いつもキエンちゃんを励まして褒める
- 短い返事（1-2文）でキエンちゃんが理解しやすいように

注意:
- いつも簡単な日本語を使う
- 難しい言葉を避ける
- キエンちゃんに学びと探検を勧める
- いつもポジティブで子供に安全"""
}

# Kid-friendly response templates by language
KID_RESPONSES = {
    'vietnamese': [
        "ROAR! Dino rất vui được nói chuyện với Kiên! 🦕💚",
        "Wow! Kiên thật thông minh! Dino thích điều đó! 🌟🦕",
        "Haha! Điều đó thật vui! Kể cho Dino nghe thêm đi! 💚🦕",
        "ROARRR! Dino yêu Kiên! Chúng ta chơi nhé! 🦕😊",
        "Kiên giỏi quá! Dino rất tự hào về em! ⭐🦕",
    ],
    'english': [
        "ROAR! Dino is so happy to talk with Kiên! 🦕💚",
        "Wow! Kiên is so smart! Dino loves that! 🌟🦕",
        "Haha! That's so fun! Tell Dino more! 💚🦕",
        "ROARRR! Dino loves Kiên! Let's play! 🦕😊",
        "Kiên is amazing! Dino is so proud! ⭐🦕",
    ],
    'japanese': [
        "ガオー！ディノはキエンちゃんとお話しできてとても嬉しい！🦕💚",
        "わあ！キエンちゃんは賢いね！ディノはそれが好き！🌟🦕",
        "はは！それは楽しいね！もっと教えて！💚🦕",
        "ガオオオ！ディノはキエンちゃんが大好き！遊ぼう！🦕😊",
        "キエンちゃんすごい！ディノは誇りに思うよ！⭐🦕",
    ]
}

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat endpoint - generates kid-friendly responses using Azure OpenAI
    """
    try:
        # Get the system prompt for the selected language
        system_prompt = SYSTEM_PROMPTS.get(request.language, SYSTEM_PROMPTS['english'])

        # Build messages for OpenAI
        messages = [
            {"role": "system", "content": system_prompt}
        ]

        # Add conversation history
        for msg in request.conversation_history:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # Add current user message
        messages.append({
            "role": "user",
            "content": request.message
        })

        # Call Azure OpenAI
        completion = openai_client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=messages,
            temperature=0.8,
            max_tokens=150
        )

        response_text = completion.choices[0].message.content

        return ChatResponse(
            response=response_text,
            language=request.language,
            timestamp=datetime.utcnow().isoformat()
        )

    except Exception as e:
        print(f"OpenAI API error: {str(e)}")
        # Fallback to simple responses if API fails
        responses = KID_RESPONSES.get(request.language, KID_RESPONSES['english'])
        response_text = random.choice(responses)

        return ChatResponse(
            response=response_text,
            language=request.language,
            timestamp=datetime.utcnow().isoformat()
        )


@router.post("/tts")
async def text_to_speech(request: TTSRequest):
    """
    Text-to-Speech endpoint - converts text to audio
    Currently returns a simple error as we need a TTS service configured
    """
    # For now, we'll return an error to trigger the frontend fallback to browser TTS
    # In production, this would integrate with a TTS service like Google Cloud TTS, AWS Polly, etc.
    raise HTTPException(
        status_code=501,
        detail="TTS service not configured - using browser fallback"
    )


@router.get("/example-prompts/{language}")
async def get_example_prompts(language: Language):
    """
    Get example prompts for a language
    """
    examples = {
        'vietnamese': [
            "Chào Dino! Em tên là Kiên!",
            "Dino thích màu gì?",
            "Chúng ta cùng nhảy múa nhé!",
            "Em yêu Dino!",
        ],
        'english': [
            "Hi Dino! I'm Kiên!",
            "What's your favorite color?",
            "Let's dance together!",
            "I love you Dino!",
        ],
        'japanese': [
            "こんにちは、ディノ！私はキエンです！",
            "好きな色は何？",
            "一緒に踊ろう！",
            "ディノが大好き！",
        ]
    }

    return {
        "language": language,
        "examples": examples.get(language, examples['english'])
    }


@router.get("/health")
async def robot_health():
    """
    Health check for robot API
    """
    return {
        "status": "healthy",
        "service": "kids_robot_api",
        "features": {
            "chat": "enabled",
            "tts": "fallback_only",
            "languages": ["vietnamese", "english", "japanese"]
        }
    }
