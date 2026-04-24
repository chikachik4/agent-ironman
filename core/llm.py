import json
import boto3
from typing import Union, List, Dict
from core.config import settings

class BedrockLLMClient:
    def __init__(self, use_sonnet=False):
        self.bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name=settings.AWS_REGION
        )
        self.model_id = settings.LLM_MODEL_EXPERT if use_sonnet else settings.LLM_MODEL_ROUTING
        
    def generate(self, prompt_or_messages: Union[str, List[Dict[str, str]]], system_prompt: str = None, max_tokens: int = 512) -> str:
        if isinstance(prompt_or_messages, str):
            messages = [{"role": "user", "content": prompt_or_messages}]
        else:
            messages = prompt_or_messages

        body_dict = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": messages
        }
        if system_prompt:
            body_dict["system"] = system_prompt
            
        try:
            response = self.bedrock.invoke_model(
                body=json.dumps(body_dict),
                modelId=self.model_id,
                accept="application/json",
                contentType="application/json"
            )
            response_body = json.loads(response.get('body').read())
            return response_body['content'][0]['text']
        except Exception as e:
            raise Exception(f"AWS Bedrock 호출 실패: {str(e)}")
