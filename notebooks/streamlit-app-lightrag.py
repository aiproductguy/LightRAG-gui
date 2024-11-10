import os
import sys
import requests
import asyncio
from contextlib import contextmanager
import logging
import PyPDF2
import xxhash
import networkx as nx
import time
import streamlit as st

# Set page config before any other Streamlit commands
st.set_page_config(
    page_title="LightRAG Demo on Streamlit",
    page_icon="😎",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        'Get help': "https://github.com/aiproductguy/LightRAG",
        'Report a bug': "https://github.com/HKUDS/LightRAG/issues",
        'About': """
        ##### LightRAG gui
        MIT open-source licensed GUI for LightRAG, a lightweight framework for retrieval-augmented generation:
        - [LightRAG Documentation](https://github.com/HKUDS/LightRAG)
        - [GUI Source Code](https://github.com/aiproductguy/LightRAG/notebooks/)
        - [Come to Demo Fridays at 12noon PT to say hi and give feedback!](https://cal.com/aiproductguy/lightrag-demo)
        - ©️ 2024 Bry at el #BothParentsMatter
        [![QRC|64](https://api.qrserver.com/v1/create-qr-code/?size=80x80&data=https://cal.com/aiproductguy/lightrag-demo)](https://cal.com/aiproductguy/lightrag-demo)
        """
    }
)

# Add the context manager right after imports
@contextmanager
def get_event_loop_context():
    """Context manager to handle asyncio event loop."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    yield loop

# Add the project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Import LightRAG packages
from lightrag import LightRAG, QueryParam
from lightrag.llm import gpt_4o_mini_complete, openai_embedding
from lightrag.utils import EmbeddingFunc, logger, set_logger

# Configure logging
working_dir = "./dickens"
if not os.path.exists(working_dir):
    os.makedirs(working_dir)
    
set_logger(os.path.join(working_dir, "lightrag.log"))
logger.setLevel(logging.DEBUG)

# Rest of the imports
import streamlit as st

# Add constants after DEFAULT_LLM_MODEL
DEFAULT_LLM_MODEL = "gpt-4o-mini-2024-07-18"
DEFAULT_EMBEDDER_MODEL = "text-embedding-ada-002"

# Add model options constants
AVAILABLE_LLM_MODELS = [
    DEFAULT_LLM_MODEL,
    "gpt-4o-mini"  # Legacy model option
]

AVAILABLE_EMBEDDER_MODELS = [
    DEFAULT_EMBEDDER_MODEL,
    "text-embedding-3-small"  # New smaller model option
]

# Move helper functions and init_rag before the UI section
def get_llm_config(model_name):
    """Get the LLM configuration based on model name."""
    if model_name in [DEFAULT_LLM_MODEL, "gpt-4o-mini"]:
        return gpt_4o_mini_complete, model_name
    else:
        raise ValueError(f"Unsupported LLM model: {model_name}")

def get_embedding_config(model_name):
    """Get the embedding configuration based on model name."""
    embedding_configs = {
        "text-embedding-ada-002": {
            "dim": 1536,
            "max_tokens": 8192
        },
        "text-embedding-3-small": {
            "dim": 1536,
            "max_tokens": 8191
        }
    }
    
    if model_name not in embedding_configs:
        raise ValueError(f"Unsupported embedding model: {model_name}")
        
    config = embedding_configs[model_name]
    api_key = get_api_key()  # Get API key securely
    if not api_key:
        raise ValueError("OpenAI API key not found")
        
    return EmbeddingFunc(
        embedding_dim=config["dim"],
        max_token_size=config["max_tokens"],
        func=lambda texts: openai_embedding(
            texts,
            model=model_name,
            api_key=api_key
        )
    )

def get_api_key():
    """Securely retrieve OpenAI API key."""
    # Check environment variable first
    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        return env_key
        
    # Then try secrets if environment variable not found
    try:
        secrets_exist = hasattr(st, "secrets") and isinstance(st.secrets, dict)
        if secrets_exist and "OPENAI_API_KEY" in st.secrets:
            os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
            return os.environ["OPENAI_API_KEY"]
    except Exception:
        pass
            
    # If no key found, show input form
    return None

def init_rag_secure(api_key: str):
    """Initialize RAG with API key without storing it."""
    working_dir = "./dickens"
    
    if not os.path.exists(working_dir):
        os.makedirs(working_dir)
    
    # Initialize RAG with current settings
    llm_func, llm_name = get_llm_config(st.session_state.settings["llm_model"])
    embedding_config = get_embedding_config(st.session_state.settings["embedding_model"])
        
    # Use API key directly without storing in session state
    llm_kwargs = {
        "temperature": st.session_state.settings["temperature"],
        "system_prompt": st.session_state.settings["system_prompt"],
        "api_key": api_key  # Use key directly
    }
    
    st.session_state.rag = LightRAG(
        working_dir=working_dir,
        llm_model_func=llm_func,
        llm_model_name=llm_name,
        llm_model_max_async=4,
        llm_model_max_token_size=32768,
        llm_model_kwargs=llm_kwargs,
        embedding_func=embedding_config
    )
    st.session_state.initialized = True

def test_api_key():
    """Test if OpenAI API key is valid and prompt for input if invalid."""
    api_key = get_api_key()
    if not api_key:
        st.error("""
        ⚠️ OpenAI API key is required.
        Please enter your API key in the form below.
        """)
        show_api_key_form()
        return False
        
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        
        # Try a simple embedding request
        response = client.embeddings.create(
            input="test",
            model="text-embedding-ada-002"
        )

        # Send test prompt
        chat_response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": "What is LightRAG?"}]
        )
        test_response = chat_response.choices[0].message.content

        # Log the test response
        add_activity_log(f"[T] Test prompt: What is LightRAG?\n[@] {test_response[:100]}...")
        
        return True
        
    except Exception as e:
        st.error(f"""
        ⚠️ API Error. Please ensure:
        1. You have entered a valid OpenAI API key
        2. Your API key has access to the text-embedding-ada-002 model
        
        Error details: {str(e)}
        """)
        
        show_api_key_form()
        return False

def show_api_key_form():
    """Display the API key input form."""
    with st.form("api_key_form"):
        new_api_key = st.text_input(
            "Enter your OpenAI API key:",
            type="password",
            help="Get your API key from https://platform.openai.com/account/api-keys"
        )
        
        submitted = st.form_submit_button("Save API Key")
        
        if submitted and new_api_key:
            os.environ["OPENAI_API_KEY"] = new_api_key
            st.session_state.initialized = False
            st.rerun()

def init_rag():
    """Initialize/reinitialize RAG."""
    api_key = get_api_key()
    if not api_key or not test_api_key_secure(api_key):
        show_api_key_form()
        return False
        
    working_dir = "./dickens"
    
    if not os.path.exists(working_dir):
        os.makedirs(working_dir)
    
    # Initialize RAG with current settings
    llm_func, llm_name = get_llm_config(st.session_state.settings["llm_model"])
    embedding_config = get_embedding_config(st.session_state.settings["embedding_model"])
        
    # Separate LLM kwargs from query settings
    llm_kwargs = {
        "temperature": st.session_state.settings["temperature"],
        "system_prompt": st.session_state.settings["system_prompt"],
        "api_key": api_key  # Use API key directly
    }
    
    st.session_state.rag = LightRAG(
        working_dir=working_dir,
        llm_model_func=llm_func,
        llm_model_name=llm_name,
        llm_model_max_async=4,
        llm_model_max_token_size=32768,
        llm_model_kwargs=llm_kwargs,
        embedding_func=embedding_config
    )
    st.session_state.initialized = True

    # Log graph stats after initialization
    graph = st.session_state.rag.chunk_entity_relation_graph._graph
    if graph:
        nodes = graph.number_of_nodes()
        edges = graph.number_of_edges()
        add_activity_log(f"[*] Records: {nodes} nodes, {edges} edges")
    
    return True

# Move title to sidebar and add activity log first
st.sidebar.markdown("### [😎 LightRAG](https://github.com/HKUDS/LightRAG) [Kwaai](https://www.kwaai.ai/) Day [🔗](https://lightrag-gui.streamlit.app)\n#beta 2024-11-09")
st.sidebar.markdown("[![QRC|64](https://api.qrserver.com/v1/create-qr-code/?size=80x80&data=https://cal.com/aiproductguy/lightrag-demo)](https://cal.com/aiproductguy/lightrag-demo)")

# Add activity log section in sidebar
st.sidebar.markdown("##### Activity Log")

# Create a sidebar container for activity logs
activity_container = st.sidebar.container()

# Add background image
st.markdown(
        f"""
        <style>
        .stApp {{
            background-image: url("https://i-blog.csdnimg.cn/direct/567139f1a36e4564abc63ce5c12b6271.jpeg");
            background-size: cover;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )


# Define all dialog functions first
@st.dialog("Insert Records")
def show_insert_dialog():
    """Dialog for inserting records from various sources."""
    tags = st.text_input(
        "Tags (optional):",
        help="Add comma-separated tags to help organize your documents"
    )
    
    tab1, tab2, tab3, tab4 = st.tabs(["Paste", "Upload", "Website", "Test"])
    
    with tab1:
        text_input = st.text_area(
            "Paste text or markdown content:",
            height=200,
            help="Paste your document content here"
        )
        
        if st.button("Insert", key="insert"):
            if text_input:
                handle_insert(text_input)
    
    with tab2:
        uploaded_file = st.file_uploader(
            "Choose a markdown file",
            type=['md', 'txt'],
            help="Upload a markdown (.md) or text (.txt) file"
        )
        
        if uploaded_file is not None:
            if st.button("Insert File", key="insert_file"):
                try:
                    content = uploaded_file.read()
                    if isinstance(content, bytes):
                        content = content.decode('utf-8')
                    handle_insert(content)
                except Exception as e:
                    st.error(f"Error inserting file: {str(e)}")
    
    with tab3:
        url = st.text_input(
            "Website URL:",
            help="Enter the URL of the webpage you want to insert"
        )
        
        if st.button("Insert", key="insert_url"):
            if url:
                try:
                    response = requests.get(url)
                    response.raise_for_status()
                    handle_insert(response.text)
                except Exception as e:
                    st.error(f"Error inserting website content: {str(e)}")
    
    with tab4:
        st.markdown("### Test Documents")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Insert A Christmas Carol"):
                try:
                    with open("dickens/inbox/book.txt", "r", encoding="utf-8") as f:
                        content = f.read()
                        handle_insert(content)
                except Exception as e:
                    st.error(f"Error inserting Dickens test book: {str(e)}")
        
        with col2:
            if st.button("Insert LightRAG Paper"):
                try:
                    with open("dickens/inbox/2410.05779v2-LightRAG.pdf", "rb") as f:
                        pdf_reader = PyPDF2.PdfReader(f)
                        content = []
                        for page in pdf_reader.pages:
                            text = page.extract_text()
                            if text.strip():  # Only add non-empty pages
                                content.append(text)
                            
                        if not content:
                            st.error("No text could be extracted from the PDF")
                        else:
                            combined_content = "\n\n".join(content)
                            handle_insert(combined_content)
                except FileNotFoundError:
                    st.error("PDF file not found. Please ensure the file exists in dickens/inbox/")
                except Exception as e:
                    st.error(f"Error inserting LightRAG whitepaper: {str(e)}")

@st.dialog("Settings")
def show_settings_dialog():
    """Dialog for configuring LightRAG settings."""
    # Update model selection dropdowns with separate options
    st.session_state.settings["llm_model"] = st.selectbox(
        "LLM Model:",
        AVAILABLE_LLM_MODELS,
        index=AVAILABLE_LLM_MODELS.index(st.session_state.settings["llm_model"])
    )
    
    st.session_state.settings["embedding_model"] = st.selectbox(
        "Embedding Model:",
        AVAILABLE_EMBEDDER_MODELS,
        index=AVAILABLE_EMBEDDER_MODELS.index(st.session_state.settings["embedding_model"])
    )
    
    st.session_state.settings["search_mode"] = st.selectbox(
        "Search mode:",
        ["naive", "local", "global", "hybrid"],
        index=["naive", "local", "global", "hybrid"].index(st.session_state.settings["search_mode"])
    )
    
    st.session_state.settings["temperature"] = st.slider(
        "Temperature:",
        min_value=0.0,
        max_value=1.0,
        value=st.session_state.settings["temperature"],
        step=0.1
    )
    
    st.session_state.settings["system_prompt"] = st.text_area(
        "System Prompt:",
        value=st.session_state.settings["system_prompt"]
    )
    
    if st.button("Apply Settings"):
        handle_settings_update()
        st.rerun()

@st.dialog("Knowledge Graph Stats", width="large")
def show_kg_stats_dialog():
    """Dialog showing detailed knowledge graph statistics and visualization."""
    try:
        # Use the correct filename in dickens directory
        graph_path = "./dickens/graph_chunk_entity_relation.graphml"
        
        if not os.path.exists(graph_path):
            st.markdown("> [!graph] ⚠️ **Knowledge Graph file not found.** Please insert some documents first.")
            return
            
        graph = nx.read_graphml(graph_path)
            
        # Basic stats
        stats = {
            "Nodes": graph.number_of_nodes(),
            "Edges": graph.number_of_edges(),
            "Average Degree": round(sum(dict(graph.degree()).values()) / graph.number_of_nodes(), 2) if graph.number_of_nodes() > 0 else 0
        }
        
        # Display stats with more detail
        st.markdown("## Knowledge Graph Statistics")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Nodes", stats["Nodes"])
        with col2:
            st.metric("Total Edges", stats["Edges"])
        with col3:
            st.metric("Average Degree", stats["Average Degree"])
        
        # Add detailed analysis
        st.markdown("## Graph Analysis")
        
        # Calculate additional metrics
        if stats["Nodes"] > 0:
            density = nx.density(graph)
            components = nx.number_connected_components(graph.to_undirected())
            
            st.markdown(f"""
            - **Graph Density:** {density:.4f}
            - **Connected Components:** {components}
            - **Most Connected Nodes:**
            """)
                        
            # Create table headers
            table_lines = [
                "| Node ID | SHA-12 | Connections |",
                "|---------|--------|-------------|"
            ]
            
            # Add rows for top nodes
            degrees = dict(graph.degree())
            top_nodes = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:5]
            for node, degree in top_nodes:
                # Get first 12 chars of SHA hash
                sha_hash = xxhash.xxh64(node.encode()).hexdigest()[:12]
                table_lines.append(f"| `{node}` | `{sha_hash}` | {degree} |")
            
            # Display the table
            st.markdown("\n".join(table_lines))
        
        # Generate visualization if there are nodes
        if stats["Nodes"] > 0:
            st.markdown("## Knowledge Graph Visualization")
            
            try:
                from pyvis.network import Network
                import random
                
                st.markdown("*Generating interactive network visualization...*")
                
                net = Network(height="600px", width="100%", notebook=True)
                net.from_nx(graph)
                
                # Apply visual styling
                for node in net.nodes:
                    node["color"] = "#{:06x}".format(random.randint(0, 0xFFFFFF))
                
                # Save and display using the same filename pattern
                html_path = "./dickens/graph_chunk_entity_relation.html"
                net.save_graph(html_path)
                
                # Display the saved HTML
                with open(html_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                st.components.v1.html(html_content, height=600)
                    
            except ImportError:
                st.markdown("⚠️ Please install pyvis to enable graph visualization: `pip install pyvis`")
            except Exception as e:
                st.markdown(f"❌ **Error generating visualization:** {str(e)}")
        
    except Exception as e:
        logger.error(f"Error getting graph stats: {str(e)}")
        st.markdown(f"❌ **Error getting graph stats:** {str(e)}")

# Move this function before the dialog definitions
def handle_chat_download():
    """Download chat history as markdown."""
    if not st.session_state.messages:
        st.error("No messages to download yet! Start a conversation first.", icon="ℹ️")
        return
        
    from time import strftime
    
    # Create markdown content
    md_lines = [
        "# LightRAG Chat Session\n",
        f"*Exported on {strftime('%Y-%m-%d %H:%M:%S')}*\n",
        "\n## Settings\n",
        f"- Search Mode: {st.session_state.settings['search_mode']}",
        f"- LLM Model: {st.session_state.settings['llm_model']}",
        f"- Embedding Model: {st.session_state.settings['embedding_model']}",
        f"- Temperature: {st.session_state.settings['temperature']}",
        f"- System Prompt: {st.session_state.settings['system_prompt']}\n",
        "\n## Conversation\n"
    ]
    
    # Add messages
    for msg in st.session_state.messages:
        role = "User" if msg["role"] == "user" else "Assistant"
        md_lines.append(f"\n### {role} ({msg['metadata'].get('timestamp', 'N/A')})")
        md_lines.append(f"\n{msg['content']}\n")
        
        if msg["role"] == "assistant" and "metadata" in msg:
            metadata = msg["metadata"]
            if "query_info" in metadata:
                md_lines.append(f"\n`> [!query] {metadata['query_info']}`")
            if "error" in metadata:
                md_lines.append(f"\n> ⚠️ Error: {metadata['error']}")
    
    md_content = "\n".join(md_lines)
    
    st.download_button(
        label="Download Chat",
        data=md_content,
        file_name=f"chat_session_{strftime('%Y%m%d_%H%M%S')}.md",
        mime="text/markdown",
        key="download_chat"
    )

def get_all_records_from_graph():
    """Extract records from the knowledge graph."""
    try:
        graph_path = "./dickens/graph_chunk_entity_relation.graphml"
        if not os.path.exists(graph_path):
            return []
            
        graph = nx.read_graphml(graph_path)
        
        records = []
        for node in graph.nodes(data=True):
            node_id, data = node
            if data.get('type') == 'chunk':
                record = {
                    'id': node_id,
                    'content': data.get('content', ''),
                    'metadata': {
                        'type': data.get('type', ''),
                        'timestamp': data.get('timestamp', ''),
                        'relationships': []
                    }
                }
                
                # Get relationships
                for edge in graph.edges(node_id, data=True):
                    source, target, edge_data = edge
                    if edge_data:
                        record['metadata']['relationships'].append({
                            'target': target,
                            'type': edge_data.get('type', ''),
                            'weight': edge_data.get('weight', 1.0)
                        })
                
                records.append(record)
        
        return records
        
    except Exception as e:
        logger.error(f"Error reading graph file: {str(e)}")
        return []

@st.dialog("Download Options")
def show_download_dialog():
    """Dialog for downloading chat history and records."""
    st.markdown("### Download Options")
    
    tab1, tab2 = st.tabs(["Chat History", "Inserted Records"])
    
    with tab1:
        st.markdown("Download the current chat session as a markdown file.")
        if "messages" not in st.session_state or not st.session_state.messages:
            st.warning("No chat history available to download.")
        else:
            handle_chat_download()
    
    with tab2:
        st.markdown("Download all inserted records as a JSON file.")
        if not hasattr(st.session_state, "rag") or st.session_state.rag is None:
            st.warning("No records available. Please initialize RAG and insert some documents first.")
            return
            
        if st.button("Download Records"):
            try:
                # Get records from graph
                records = get_all_records_from_graph()
                
                if not records:
                    st.warning("No records found to download.")
                    return
                
                import json
                from time import strftime
                
                # Convert records to JSON
                records_json = json.dumps(records, indent=2)
                
                # Create download button
                st.download_button(
                    label="Download JSON",
                    data=records_json,
                    file_name=f"lightrag_records_{strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
                
                # Log success
                add_activity_log(f"[↓] Downloaded {len(records)} records")
                
            except Exception as e:
                logger.error(f"Error downloading records: {str(e)}")
                st.error(f"Error downloading records: {str(e)}")
                add_activity_log(f"[!] Download error: {str(e)}")

# Now add the buttons after all dialogs are defined
col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("➕", help="Insert Records"):
        show_insert_dialog()

with col2:
    if st.button("⚙", help="Settings"):
        show_settings_dialog()

with col3:
    if st.button("፨", help="Knowledge Graph Stats"):
        show_kg_stats_dialog()

with col4:
    if st.button("⬇", help="Download Options"):
        show_download_dialog()

# Create a container for chat history and AI output with border
chat_container = st.container(border=True)

# Add after the model constants but before session state initialization
def add_activity_log(message: str):
    """Add an entry to the activity log and display in sidebar."""
    # Initialize activity log if not exists
    if "activity_log" not in st.session_state:
        st.session_state.activity_log = []
        
    # Add new message
    st.session_state.activity_log.append(message)
    
    # Keep only last 50 entries to prevent too much history
    st.session_state.activity_log = st.session_state.activity_log[-50:]
    
    # Update sidebar display
    with activity_container:
        st.markdown(f"```\n{message}\n```")

# Move this function before any chat handling code, right after the add_activity_log function

def format_chat_message(content, metadata=None):
    """Format chat message with markdown and metadata."""
    formatted = []
    
    # Add main content with markdown formatting
    formatted.append(f"```\n"+content+"\n```")
    
    # Add metadata footer if present
    if metadata:
        if "query_info" in metadata:
            formatted.append(f"`> [!query] {metadata['query_info']}`")
        if "error" in metadata:
            formatted.append(f"> ⚠️ **Error:** {metadata['error']}")
            
    return "\n".join(formatted)

# Move this function before the chat handling code, right after format_chat_message

def rewrite_prompt(prompt: str) -> str:
    """Rewrite the user prompt into a templated format using OpenAI."""
    try:
        from openai import OpenAI
        api_key = get_api_key()  # Get API key using our utility function
        if not api_key:
            raise ValueError("OpenAI API key not found")
            
        client = OpenAI(api_key=api_key)
        
        system_instruction = f"""
        You are a prompt engineering assistant. Your task is to rewrite user prompts into a templated format.
        The template should follow this structure:

        <START_OF_SYSTEM_PROMPT>
        {st.session_state.settings["system_prompt"]}
        {{# Optional few shot demos if provided #}}
        {{% if few_shot_demos is not none %}}
        Here are some examples:
        {{few_shot_demos}}
        {{% endif %}}
        <END_OF_SYSTEM_PROMPT>
        <START_OF_USER>
        {{input_str}}
        <END_OF_USER>

        Keep the original intent but make it more specific and detailed.
        You will answer a reasoning question. Think step by step. The last two lines of your response should be of the following format: 
        - '> Answer: $VALUE' where VALUE is concise and to the point.
        - '> Sources: $SOURCE1, $SOURCE2, ...' where SOURCE1, SOURCE2, etc. are the sources you used to justify your answer.
        """

        response = client.chat.completions.create(
            model="gpt-4",  # Using GPT-4 for better prompt engineering
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"Rewrite this prompt: {prompt}"}
            ],
            temperature=0.7
        )
        
        rewritten = response.choices[0].message.content
        
        # Log the rewrite
        add_activity_log(f"[*] Prompt rewritten ({len(prompt)} → {len(rewritten)} chars)")
        
        return rewritten
        
    except Exception as e:
        logger.error(f"Error rewriting prompt: {str(e)}")
        add_activity_log(f"[!] Prompt rewrite error: {str(e)}")
        # Return original prompt if rewrite fails
        return prompt

def test_api_key_secure(api_key: str) -> bool:
    """Test if OpenAI API key is valid without storing it."""
    if not api_key:
        return False
        
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        
        # Try a simple embedding request
        response = client.embeddings.create(
            input="test",
            model="text-embedding-ada-002"
        )

        # Send test prompt
        chat_response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": "What is LightRAG?"}]
        )
        test_response = chat_response.choices[0].message.content

        # Log the test response
        add_activity_log(f"[T] Test prompt: What is LightRAG?\n[@] {test_response[:100]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"API key test failed: {str(e)}")
        add_activity_log(f"[!] API key test failed: {str(e)}")
        return False

# Initialize session state with API key
if "initialized" not in st.session_state:
    st.session_state.initialized = False
    st.session_state.settings = {
        "search_mode": "hybrid",
        "llm_model": DEFAULT_LLM_MODEL,
        "embedding_model": DEFAULT_EMBEDDER_MODEL,
        "system_prompt": """You are a helpful AI assistant that answers questions based on the provided records.
        
        Guidelines:
        1. Use Obsidian markdown format with ## headers, #tags, [[wikilinks]], and whitespace
        2. Cite relevant sources when possible
        3. Be concise but thorough
        4. If uncertain, acknowledge limitations
        5. Format code blocks with appropriate language tags
        
        Remember to maintain a helpful and professional tone while providing accurate information based on the context.""",
        "temperature": 0.7
    }
    
    # Initialize messages list if not exists
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Check for API key in different locations
    api_key = get_api_key()
    if api_key:
        if test_api_key_secure(api_key):
            st.session_state.temp_api_key = api_key
            init_rag_secure(api_key)
        else:
            st.error("Invalid API key found in environment/secrets.")
            show_api_key_form()
    else:
        show_api_key_form()

# After initializing RAG, display initial stats
with chat_container: 
    if not st.session_state.initialized and hasattr(st.session_state, 'temp_api_key'):
        init_rag_secure(st.session_state.temp_api_key)
        # Clear temporary key after initialization
        delattr(st.session_state, 'temp_api_key')

# Define helper functions first
def handle_settings_update():
    """Update settings and force RAG reinitialization."""
    st.session_state.initialized = False  # Force reinitialization

# Add a visual separator for action footer
if prompt := st.chat_input("Ask away. Expect 60+ seconds processing. Patience in precision. "):
    add_activity_log(f"> Q: {prompt[:50]}..." if len(prompt) > 50 else f"> Q: {prompt}")

    prompt_rewritten = rewrite_prompt(prompt)
    # Create query info string
    prompt_hash = xxhash.xxh64(prompt.encode()).hexdigest()[:12]
    current_date = time.strftime('%Y-%m-%d %H:%M:%S')
    query_info = f"[{current_date}] {st.session_state.settings['search_mode']}@{st.session_state.settings['llm_model']} #{prompt_hash}"
    
    # Add user message with markdown
    with st.chat_message("user"):
        with st.expander(f"> Prompt: {prompt[:50]}..."):
            st.markdown(f"```\n{prompt_rewritten}\n```")                # Add date and prompt hash
            st.markdown(f"`> [!query] {query_info}`")

    # Generate response
    with st.chat_message("assistant"):
        status_placeholder = st.empty()
        
        with status_placeholder.status("Searching and generating response..."):
            query_param = QueryParam(mode=st.session_state.settings["search_mode"])
            try:
                start_time = time.time()  # Start timing
                with get_event_loop_context() as loop:
                    response = loop.run_until_complete(st.session_state.rag.aquery(prompt_rewritten, param=query_param))                
                query_runtime = round(time.time() - start_time, 2)  # Calculate runtime
                add_activity_log(f"Query #{prompt_hash} runtime: {query_runtime}s")

                # Create metadata
                metadata = {
                    "timestamp": time.strftime('%H:%M:%S'),
                    "search_mode": st.session_state.settings["search_mode"],
                    "llm_model": st.session_state.settings["llm_model"],
                    "embedding_model": st.session_state.settings["embedding_model"],
                    "temperature": st.session_state.settings["temperature"],
                    "prompt_hash": prompt_hash,
                    "query_info": query_info,
                    "runtime": f"{query_runtime}s"  # Add runtime to metadata
                }
                
                # Format and display response with markdown
                formatted_response = format_chat_message(response, metadata)
                st.markdown(formatted_response)
                
                # Add to message history
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response,
                    "metadata": metadata
                })
                
                # Log the response
                add_activity_log(f"> A: {response[:50]}..." if len(response) > 50 else f"[@] A: {response}")
                
            except Exception as e:
                error_msg = f"Error generating response: {str(e)}"
                logger.error(error_msg)
                add_activity_log(f"[!] {error_msg}")
                
                fallback_response = "I apologize, but I encountered an error while processing your request."
                error_metadata = {
                    "timestamp": time.strftime('%H:%M:%S'),
                    "error": str(e)
                }
                
                # Format and display error response with markdown
                formatted_error = format_chat_message(fallback_response, error_metadata)
                st.markdown(formatted_error)
                
                # Add to message history
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": fallback_response,
                    "metadata": error_metadata
                })
                
                # Log the error
                add_activity_log(f"[!] {error_msg}")

# Modify handle_insert to use add_activity_log
def handle_insert(content):
    """Handle document insertion."""
    # First check if RAG is initialized
    if not hasattr(st.session_state, "rag") or st.session_state.rag is None:
        # Try to initialize RAG
        api_key = get_api_key()
        if not api_key:
            st.error("Please provide your OpenAI API key first.")
            show_api_key_form()
            return
        if not test_api_key_secure(api_key):
            return
        init_rag_secure(api_key)
    
    try:
        # Verify API key is still working
        if not test_api_key():
            return
            
        with st.spinner("Inserting content..."):
            # Log the content size for debugging
            add_activity_log(f"[*] Processing content ({len(content)} chars)...")
            
            with get_event_loop_context() as loop:
                success = loop.run_until_complete(st.session_state.rag.ainsert(content))
                
                if success:
                    st.success("Content inserted successfully!")
                    add_activity_log(f"[+] Added content ({len(content)} chars)")
                else:
                    st.error("Failed to insert content - no relationships extracted")
                    add_activity_log("[-] Failed to extract relationships from content")
                    
    except Exception as e:
        logger.exception("An error occurred during insertion.")
        st.error(f"An error occurred: {e}")
        add_activity_log(f"[!] Insert error: {str(e)}")
