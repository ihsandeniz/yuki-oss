"""Demo MCP sunucusu — MCP boru hattı KANITI (Faz 23). Kimlik bilgisi gerektirmez.

Yuki'nin MCP client köprüsünün gerçekten bağlanıp araç listeleyip çağırdığını
doğrulamak için minimal bir stdio MCP sunucusu. Üretimde kullanılmaz.

Çalıştırma (stdio): python app/services/mcp_demo_server.py
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("alice-demo")


@mcp.tool()
def echo(text: str) -> str:
    """Verilen metni aynen geri döndürür (boru hattı kanıtı)."""
    return f"echo: {text}"


@mcp.tool()
def add(a: int, b: int) -> int:
    """İki tam sayıyı toplar."""
    return a + b


if __name__ == "__main__":
    mcp.run(transport="stdio")
