from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from openai import OpenAI
import json
import os
from dotenv import load_dotenv
import httpx

app = FastAPI()

load_dotenv()

# Request model
class SEORequest(BaseModel):
    team_names: str
    title: str
    post_id: int

# Initialize the OpenAI client
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# Configure WordPress API settings
WORDPRESS_API_URL = os.getenv("WORDPRESS_API_URL")
WORDPRESS_API_KEY = os.getenv("WORDPRESS_API_KEY")

async def update_wordpress_seo(wp_url: str, api_key: str, prompt: str, post_id: int):
    """Background task to update WordPress content"""
    try:
        response = client.chat.completions.create(
            model="deepseek-reasoner",
            temperature=0.7,
            messages=[
                {"role": "system", "content": "You are a helpful SEO assistant"},
                {"role": "user", "content": prompt}
            ],
            stream=False
        )

        # Process DeepSeek response
        raw_content = response.choices[0].message.content
        json_str = raw_content.split('```json')[1].split('```')[0].strip() if '```json' in raw_content else raw_content
        seo_data = json.loads(json_str)
        
        # Prepare WordPress payload
        wp_payload = {
            "post_id": post_id,
            "content": f"{', '.join(seo_data['content'])}\n{', '.join(seo_data['description'])}",
            "_yoast_wpseo_metadesc": seo_data["meta_description"],
            "_yoast_wpseo_focuskw": seo_data["keywords"]
        }
        
        async with httpx.AsyncClient() as _client:
            response = await _client.post(
                wp_url,
                json=wp_payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
            )
            if response.status_code != 200:
                # Implement proper error logging here
                print(f"WordPress update failed: {response.text}")
            print("WordPress update successful")
    except Exception as e:
        # Log exceptions
        print(f"Exception during WordPress update: {str(e)}")

@app.post("/generate-and-update-seo")
async def generate_and_update_seo(request: SEORequest, background_tasks: BackgroundTasks):
    """
    Endpoint that:
    1. Generates SEO content using DeepSeek
    2. Queues WordPress update as background task
    """
    try:
        # Step 1: Generate SEO content with DeepSeek
        prompt = f"""Return a JSON formatted like:
        {{
            "content": "...",
            "meta_description": "...",
            "keywords": "...",
            "description": "..."
        }}
        For content, generate multiple short name variations for {request.team_names} to optimize search queries. Include abbreviations, nicknames, and different spellings. 
        For meta_description and keywords, use combinations of team names with this title: {request.title}.
        For description,  generate multiple short name variations for {request.title} to optimize search queries. Include abbreviations and different spellings.
        The keywords should be relevant to the content and title and it can be a maximum of 191 characters.
        """
        
        # Add WordPress update to background tasks
        background_tasks.add_task(
            update_wordpress_seo,
            WORDPRESS_API_URL,
            WORDPRESS_API_KEY,
            prompt,
            request.post_id
        )

        return {"message": "SEO generation complete. WordPress update queued in background."}

    except json.JSONDecodeError as e:
        raise HTTPException(500, f"JSON error: {str(e)}")
    except KeyError as e:
        raise HTTPException(500, f"Missing key: {str(e)}")
    except Exception as e:
        raise HTTPException(500, f"Operation failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
