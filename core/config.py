import os
from typing import Dict
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

class ClusterConfig(BaseModel):
    name: str
    api_url: str
    prometheus_url: str
    is_active: bool = True

class Settings(BaseSettings):
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "test")
    PROJECT_PREFIX: str = "test-" if ENVIRONMENT == "test" else "bookjjeok-cloud-"
    
    # VPC3 (Management Hub) Config
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    OPENSEARCH_URL: str = os.getenv("OPENSEARCH_URL", "https://localhost:9200")
    
    # AWS Bedrock Config
    AWS_REGION: str = os.getenv("AWS_REGION", "ap-northeast-2")
    LLM_MODEL_ANALYST: str = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    LLM_MODEL_EXECUTION: str = "anthropic.claude-3-haiku-20240307-v1:0"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def CLUSTERS(self) -> Dict[str, ClusterConfig]:
        if self.ENVIRONMENT == "test":
            # Sandbox Environment (Test)
            vpc1_ip = os.getenv("VPC1_PRIVATE_IP", "127.0.0.1")
            return {
                "vpc1": ClusterConfig(
                    name=f"{self.PROJECT_PREFIX}sandbox-k3s",
                    api_url=f"https://{vpc1_ip}:6443",
                    prometheus_url=f"http://{vpc1_ip}:30090"
                )
            }
        else:
            # Production Environment (EKS + On-prem K8s)
            eks_endpoint = os.getenv("EKS_CLUSTER_ENDPOINT", "https://eks.amazonaws.com")
            vpc1_prom = os.getenv("VPC1_PROMETHEUS_IP", "localhost")
            
            vpc2_k8s = os.getenv("VPC2_K8S_ENDPOINT", "https://onprem.local:6443")
            vpc2_prom = os.getenv("VPC2_PROMETHEUS_IP", "localhost")
            
            return {
                "vpc1": ClusterConfig(
                    name=f"{self.PROJECT_PREFIX}prod-eks",
                    api_url=eks_endpoint,
                    prometheus_url=f"http://{vpc1_prom}:9090"
                ),
                "vpc2": ClusterConfig(
                    name=f"{self.PROJECT_PREFIX}onprem-k8s",
                    api_url=vpc2_k8s,
                    prometheus_url=f"http://{vpc2_prom}:9090",
                    is_active=False  # 추후 On-prem 연동 완료 시 True로 변경 가능
                )
            }

settings = Settings()
