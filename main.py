from fastapi import FastAPI, HTTPException
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
WORDPRESS_API_URL = os.getenv("WORDPRESS_API_URL")  # e.g., "https://your-wordpress-site.com/wp-json/wp/v2/posts"
WORDPRESS_API_KEY = os.getenv("WORDPRESS_API_KEY")  # Store in environment variables!

@app.post("/generate-and-update-seo")
async def generate_and_update_seo(request: SEORequest):
    """
    Endpoint that:
    1. Generates SEO content using DeepSeek
    2. Updates WordPress through your custom endpoint
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
        For content, generate multiple short name variations for {request.team_names} to optimize search queries, including abbreviations, nicknames, and different spellings. 
        For meta_description and keywords, use combinations of team names with this title: {request.title}.
        For description,  generate multiple short name variations for {request.title} to optimize search queries, including abbreviations, nicknames, and different spellings.
        The keywords should be relevant to the content and title and it can be a maximum of 191 characters.
        """
        
        response = client.chat.completions.create(
            model="deepseek-chat",
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
        
        # # Step 2: Update WordPress
        wp_payload = {
            "post_id": request.post_id,
            "content": f"{', '.join(seo_data['content'])}\n{', '.join(seo_data['description'])}",
            "_yoast_wpseo_metadesc": seo_data["meta_description"],
            "_yoast_wpseo_focuskw": seo_data["keywords"]  # Take first keyword
        }

        async with httpx.AsyncClient() as _client:
            wp_response = await _client.post(
                WORDPRESS_API_URL,
                json=wp_payload,
                headers={
                    "Authorization": f"Bearer {WORDPRESS_API_KEY}",
                    "Content-Type": "application/json"
                }
            )

            if wp_response.status_code != 200:
                raise HTTPException(
                    status_code=wp_response.status_code,
                    detail=f"WordPress update failed: {wp_response.text}"
                )

        return {
            "message": "SEO updated successfully"
        }

    except json.JSONDecodeError as e:
        raise HTTPException(500, f"JSON error: {str(e)}")
    except KeyError as e:
        raise HTTPException(500, f"Missing key: {str(e)}")
    except Exception as e:
        raise HTTPException(500, f"Operation failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    
