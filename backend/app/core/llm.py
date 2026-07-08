# app/core/llm.py
import os
from langchain_openai import ChatOpenAI

class LLMManager:
    """Manages LLM initialization and interactions"""
    
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",   # ✅ mini model
            api_key=api_key,
            temperature=0.3,
            max_tokens=200,
        )
    
    async def generate_response(self, messages):
        """Generate response from LLM"""
        try:
            response = await self.llm.ainvoke(messages)
            return response.content.strip()
        except Exception as e:
            print("LLM error:", e)
            raise