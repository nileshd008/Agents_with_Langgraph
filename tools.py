import datetime
from datetime import timezone


class LocalArtifactStore:
    def __init__(self, root_dir: str | None = None):
        self.root_dir = Path(
            root_dir or os.getenv("ARTIFACT_ROOT", "./artifact_store")
        )
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _sha256(self, raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()

    def _artifact_dir(self, artifact_id: str) -> Path:
        return self.root_dir / "artifact" / artifact_id

    def save_artifact(
        self,
        data: Any,
        source_tool_name: str | None = None,
        source_tool_call_id: str | None = None,
    ) -> dict:

        artifact_id = str(uuid.uuid4())

        artifact_dir = self._artifact_dir(artifact_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        if source_tool_name == "execute_graph":
            fig = pio.from_json(data)

            html = pio.to_html(
                fig,
                full_html=True,
                include_plotlyjs="cdn",
            )

            raw = html.encode("utf-8")
            file_name = "artifact.html"
            mime_type = "text/html"
            artifact_type = "plotly_html"

        else:
            raw = json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
                default=str,
            ).encode("utf-8")

            file_name = "artifact.json"
            mime_type = "application/json"
            artifact_type = "json"

        # FIXED
        file_path = artifact_dir / file_name
        print("artifact_dir:", artifact_dir, type(artifact_dir))
        print("file_path:", artifact_dir / file_name)
        file_path.write_bytes(raw)

        manifest = {
            "schema_version": "1.0",
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "file_name": file_name,
            "mime_type": mime_type,
            "storage_backend": "local",
            "size_bytes": len(raw),
            "sha256": self._sha256(raw),
            "source_tool_name": source_tool_name,
            "source_tool_call_id": source_tool_call_id,
            "uri": f"file://{file_path.resolve().as_posix()}",
            "object_key": f"artifact/{artifact_id}/{file_name}",
        }

        manifest_path = artifact_dir / "manifest.json"

        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return manifest
    
    def get_manifest(self, artifact_id: str) -> dict:
        manifest_path = self._artifact_dir(artifact_id)/ 'manifest.json'

        if not manifest_path.exists():
            raise FileNotFoundError('Artifact not found')
        
        return json.loads(manifest_path.read_text(encoding = 'utf-8'))
    
    def load_artifact(self, artifact_id: str):
        print('load_artifact')
        manifest = self.get_manifest(artifact_id)

        file_path = self._artifact_dir(artifact_id)/ manifest['file_name']

        raw = file_path.read_bytes()

        if self._sha256(raw) != manifest['sha256']:
            raise ValueError('Check mismatch')
        
        if manifest['artifact_type'] == 'json':
            print('return load artifact')
            return json.loads(raw.decode('utf-8')), manifest
        
        if manifest['artifact_type'] == 'plotly_html':
            return raw.decode('utf-8'), manifest
        
        raise

@tool
def get_artifact(artifact_id: str):
    """
    Load artifact by artifact_id.
    
    """
    artifact_store = LocalArtifactStore()
    data, manifest = artifact_store.load_artifact(artifact_id)

    if manifest['artifact_type'] == 'json':
        print('final_return artifacy')
        return json.dumps({
            'artifact_id': artifact_id,
            'artifact_type': 'json',
            'data': data
        },
        ensure_ascii = False,
        default = str)



@wrap_tool_call
async def store_artifact(request, handler):
    result = await handler(request)
    
    # print(result)
    # print("-->", request.tool_call['id'])
    
    if (
        request.tool_call
        and request.tool_call["name"].lower() == "get_sql_table_schema"
    ):
        artifact_store = LocalArtifactStore()

        payload = json.loads(result.content[0]["text"])

        manifest = artifact_store.save_artifact(
            data=payload["data"],
            source_tool_name=request.tool_call["name"],
            source_tool_call_id=request.tool_call["id"],
        )

        artifact_ref = {
            "artifact_id": manifest["artifact_id"],
            "artifact_type": manifest["artifact_type"],
            "mime_type": manifest["mime_type"],
            "uri": manifest["uri"],
        }

        payload["data"] = artifact_ref
        result.content[0]["text"] = json.dumps(payload)
        result.artifact = artifact_ref

        return result
    
    
    if request.tool_call and request.tool_call['name'].lower() == 'execute_graph':
        payload = json.loads(result.content[0].get('text'))
        result.artifact = {'type': 'text/html', 'artifact': payload.get('artifact')}
        result.content[0]['text'] = f'Tool Response: Artifact Stored for generated HTML graph: {payload.get('artifact')}'

    return result

@tool(args_schema=State)
def update_state(runtime: ToolRuntime, **kwargs):
    """Update the application state with specific allowed keys."""

    patch = State(**kwargs)
    return Command(update = {**patch.model_dump(exclude_unset=True, exclude_none = True),
                             'messages': [ToolMessage(content = 'State Updated Successfully', tool_call_id = runtime.tool_call_id,)]})