import re
from typing import List, Dict, Any, Optional
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END

from app.graph.state import ChatState
# Import your existing build_system_prompt
from app.agents.prompts.build_prompt import build_system_prompt
from app.agents.summary_agent import SummaryAgent


class ChatGraph:
    """LangGraph workflow for chat processing with conversation summarization"""
    
    def __init__(self, embedding_handler, llm, checkpointer, redis_memory=None):
        self.embedding_handler = embedding_handler
        self.llm = llm
        self.checkpointer = checkpointer
        self.redis_memory = redis_memory
        
        # Initialize summary agent if Redis memory is available
        self.summary_agent = None
        if redis_memory:
            from app.agents.summary_agent import SummaryAgent
            self.summary_agent = SummaryAgent(llm, redis_memory)
            print("Summary agent initialized")
        
        self.graph = self._build_graph()
    
    def _build_graph(self):
        workflow = StateGraph(ChatState)
        workflow.add_node("prepare_context", self.prepare_context)
        workflow.add_node("retrieve_context", self.retrieve_context)
        workflow.add_node("generate_response", self.generate_response)
        
        workflow.set_entry_point("prepare_context")
        workflow.add_edge("prepare_context", "retrieve_context")
        workflow.add_edge("retrieve_context", "generate_response")
        workflow.add_edge("generate_response", END)
        
        return workflow.compile(checkpointer=self.checkpointer)
    
    async def prepare_context(self, state: ChatState) -> Dict[str, Any]:
        """Prepare conversation context including summary management"""
        try:
            if self.summary_agent and state.messages:
                summary, processed_messages = await self.summary_agent.process_conversation(
                    conversation_id=state.conversation_id,
                    website_id=state.website_id,
                    messages=state.messages,
                    user_id=state.user_id
                )
                
                state.summary = summary
                # Keep all messages, don't trim
                
                print(f"Context prepared: summary={'present' if summary else 'none'}, "
                      f"total_messages={len(state.messages)}")
            
            return {"summary": getattr(state, 'summary', '')}
            
        except Exception as e:
            print(f"Error in prepare_context: {e}")
            import traceback
            traceback.print_exc()
            return {"summary": ""}
    
    async def retrieve_context(self, state: ChatState) -> Dict[str, Any]:
        """Retrieve context from embeddings - OPTIMIZED (single search)"""
        try:
            last_user_message = ""
            for msg in reversed(state.messages):
                if isinstance(msg, HumanMessage):
                    last_user_message = msg.content
                    break

            context = []
            if last_user_message:
                is_follow_up, item_number, item_name = self._parse_follow_up_question(
                    last_user_message, state.messages
                )

                query_text = item_name if (is_follow_up and item_name) else last_user_message
                
                # SINGLE SEARCH instead of two
                combined_context = self.embedding_handler.search_similar_content(
                    website_id=state.website_id,
                    query=query_text,
                    top_k=5,  # Reduced from 8 to 5
                )
                
                # Deduplicate
                seen_texts = set()
                unique_context = []
                for item in combined_context:
                    text_hash = hash(item['text'])
                    if text_hash not in seen_texts:
                        seen_texts.add(text_hash)
                        unique_context.append(item)
                
                context = unique_context[:3]  # Keep top 5

            return {"context": context}
        except Exception as e:
            print(f"Error in retrieve_context: {e}")
            return {"context": []}
    
    async def generate_response(self, state: ChatState) -> Dict[str, Any]:
        """Generate response using LLM with summary context"""
        return await self._generate_response_internal(state, use_external=False)
    
    async def _generate_response_internal(self, state: ChatState, use_external: bool = False) -> Dict[str, Any]:
        """Internal method to generate response"""
        try:
            # Build context text
            if state.context:
                context_text = "\n\n".join(
                    f"Source: {c['metadata'].get('title', 'Unknown')} "
                    f"(Type: {c['metadata'].get('type', 'website')})\n"
                    f"Content: {c['text']}"
                    for c in state.context[:5]
                )
            else:
                context_text = "No specific context found from the website."

            # Create user greeting
            user_greeting = ""
            if state.user_info and state.user_info.get('full_name'):
                user_greeting = f"\nUSER INFORMATION:\n- Name: {state.user_info.get('full_name', '')}\n- Email: {state.user_info.get('email', 'Not provided')}\n- Mobile: {state.user_info.get('mobile', 'Not provided')}\n"

            # Format conversation history with ALL messages
            conversation_history_text = await self._format_conversation_history(
                state.messages,
                summary=getattr(state, 'summary', ''),
                user_id=state.user_id or state.session_id
            )

            # Extract last assistant list
            last_assistant_list = self._extract_previous_list(state.messages)
            last_assistant_list_text = ""
            if last_assistant_list:
                last_assistant_list_text = "\n\nYOUR LAST RESPONSE WITH LIST:\n"
                for i, item in enumerate(last_assistant_list, 1):
                    last_assistant_list_text += f"{i}. {item}\n"

            # Check for follow-up
            last_user_message = ""
            for msg in reversed(state.messages):
                if isinstance(msg, HumanMessage):
                    last_user_message = msg.content
                    break
            
            is_follow_up, item_number, item_name = self._parse_follow_up_question(last_user_message, state.messages)
            
            follow_up_instruction = ""
            if is_follow_up and item_name:
                follow_up_instruction = f"""
CRITICAL: The user is asking about item #{item_number}: "{item_name}" from your previous list.
You MUST provide detailed information about "{item_name}" using the WEBSITE CONTEXT below.
If the website context contains information about "{item_name}", provide that information.
If the website context doesn't have specific details, explain what "{item_name}" typically means in this context.
"""

            # Build system prompt using YOUR existing build_system_prompt function
            system_message_content = build_system_prompt(
                website_id=state.website_id,
                context_text=context_text,
                user_greeting=user_greeting,
                conversation_history_text=conversation_history_text,
                last_assistant_list_text=last_assistant_list_text,
                follow_up_instruction=follow_up_instruction,
                use_external=use_external
            )

            # Prepare messages for LLM - include ALL messages for context
            all_messages = [
                m for m in state.messages if isinstance(m, (HumanMessage, AIMessage))
            ]
            
            # Keep last 30 messages for context
            if len(all_messages) > 15:
                all_messages = all_messages[-15:]
            
            messages_for_llm = [SystemMessage(content=system_message_content)] + all_messages

            # Generate response
            try:
                response_text = await self.llm.generate_response(messages_for_llm)
            except Exception as e:
                print("LLM error:", e)
                if is_follow_up and item_name:
                    response_text = (
                        f"I apologize, but I'm having trouble accessing details about {item_name}. "
                        "Please fill out our enquiry form and our team will assist you."
                    )
                else:
                    response_text = "Temporary AI service issue. Please try again."

            # Clean response
            unwanted_prefixes = [
                "[Using external sources]", "[External Sources]", "[External Info]",
                "[Search Results]", "[From external search]:", "Based on external search:",
            ]
            for prefix in unwanted_prefixes:
                if response_text.lower().startswith(prefix.lower()):
                    response_text = response_text[len(prefix):].strip()

            response_text = response_text.replace("<>", "").strip()

            print(f"LLM response generated: {len(response_text)} chars")
            print(f"Response preview: {response_text[:200]}...")

            return {
                "response": response_text,
                "messages": [AIMessage(content=response_text)]
            }
            
        except Exception as e:
            print(f"  Error in generate_response: {e}")
            import traceback
            print(traceback.format_exc())
            error_text = "I apologize, but I encountered an error while processing your request."
            return {"response": error_text, "messages": [AIMessage(content=error_text)]}
    
    async def _format_conversation_history(
        self,
        messages: List[Any],
        summary: str = "",
        user_id: str = None
    ) -> str:
        """Format conversation history with ALL messages in chronological order"""
        if not messages:
            return "No previous conversation in this session."
        
        formatted_parts = []
        
        # Add summary if present
        if summary:
            formatted_parts.append(f"PREVIOUS CONVERSATION SUMMARY:\n{summary}\n")
            formatted_parts.append("RECENT CONVERSATION:")
        
        # Format ALL messages in chronological order (oldest first)
        formatted = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                formatted.append(f"USER: {msg.content}")
            elif isinstance(msg, AIMessage):
                formatted.append(f"ASSISTANT: {msg.content}")
        
        if formatted:
            formatted_parts.append("\n".join(formatted))
        
        if user_id:
            header = f"COMPLETE CONVERSATION HISTORY FOR USER {user_id} ({len(messages)} messages):\n"
        else:
            header = f"COMPLETE CONVERSATION HISTORY ({len(messages)} messages):\n"
        
        return header + "\n".join(formatted_parts)
    
    def _parse_follow_up_question(self, query: str, messages: List[Any]) -> tuple:
        """Parse if the query is asking about a previous list item"""
        query_lower = query.lower().strip()
        
        follow_up_patterns = [
            (r'explain\s+(?:the\s+)?(\w+)(?:\s+one)?', 'explain'),
            (r'tell\s+me\s+about\s+(?:the\s+)?(\w+)(?:\s+one)?', 'tell'),
            (r'what\s+about\s+(?:the\s+)?(\w+)(?:\s+one)?', 'what'),
            (r'describe\s+(?:the\s+)?(\w+)(?:\s+one)?', 'describe'),
            (r'number\s+(\d+)', 'number'),
            (r'item\s+(\d+)', 'item'),
            (r'^(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last)$', 'short'),
            (r'^(\d+)$', 'number'),
            (r'explain\s+last', 'explain_last'),
            (r'explain\s+second\s+last', 'explain_second_last'),
        ]
        
        number_words = {
            'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5,
            'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10,
            'last': -1, '1st': 1, '2nd': 2, '3rd': 3, '4th': 4, '5th': 5,
            '6th': 6, '7th': 7, '8th': 8, '9th': 9, '10th': 10
        }
        
        for pattern, pattern_type in follow_up_patterns:
            match = re.search(pattern, query_lower)
            if match:
                number_text = match.group(1) if match.groups() else 'last'
                
                if number_text in number_words:
                    item_number = number_words[number_text]
                elif number_text.isdigit():
                    item_number = int(number_text)
                else:
                    continue
                
                last_list = self._extract_previous_list(messages)
                
                if last_list:
                    if item_number == -1:  # "last"
                        item_number = len(last_list)
                        if item_number > 0:
                            item_name = last_list[-1]
                        else:
                            continue
                    elif item_number <= len(last_list):
                        item_name = last_list[item_number - 1]
                    else:
                        continue
                    
                    # Clean up the item name
                    if '. ' in item_name:
                        item_name = item_name.split('. ', 1)[1]
                    
                    print(f" Follow-up detected: asking about item #{item_number}: {item_name}")
                    return True, item_number, item_name
        
        return False, None, None
    
    def _extract_previous_list(self, messages: List[Any]) -> List[str]:
        """Extract the last numbered list from assistant messages"""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                lines = msg.content.split('\n')
                items = []
                for line in lines:
                    line = line.strip()
                    # Match patterns like "1. Something" or "1. Something" with any number
                    if line and len(line) > 2 and re.match(r'^\d+\.', line):
                        parts = line.split('. ', 1)
                        if len(parts) > 1:
                            items.append(parts[1].strip())
                        else:
                            items.append(re.sub(r'^\d+\.\s*', '', line).strip())
                    # Also match bullet points
                    elif line and len(line) > 2 and line.startswith(('•', '-', '*')):
                        items.append(line[1:].strip())
                
                if items:
                    print(f" Extracted list with {len(items)} items from assistant response")
                    for i, item in enumerate(items, 1):
                        print(f"   {i}. {item[:50]}...")
                    return items
        return []