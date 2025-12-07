from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, field_validator

# Initialize FastAPI app
app = FastAPI(title="Universal Website Scraper")

# Add validation error handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    
    # Format errors for JSON serialization
    formatted_errors = []
    for error in errors:
        formatted_errors.append({
            "field": error.get("loc", []),
            "message": error.get("msg", "Validation error")
        })
    
    return JSONResponse(
        status_code=422,
        content={"error": "Invalid request", "details": formatted_errors}
    )

# Setup templates
templates = Jinja2Templates(directory="app/template")

# Request model
class ScrapeRequest(BaseModel):
    url: str
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v):
        # Strip whitespace
        v = v.strip()
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v

# Health check endpoint
@app.get("/healthz")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}

# Root endpoint - serves frontend
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the frontend HTML page"""
    return templates.TemplateResponse("index.html", {"request": request})

# Scrape endpoint
@app.post("/scrape")
async def scrape_url(request: ScrapeRequest):
    """
    Scrape a website and return structured JSON
    """
    try:
        # Import scraper
        from app.scraper import scrape_website
        
        # Perform scraping
        result = await scrape_website(request.url)
        
        return {"result": result}
        
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"error": str(e)}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Scraping failed: {str(e)}"}
        )

# Optional: Add CORS if needed
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)