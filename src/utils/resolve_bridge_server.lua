--[[
  DaVinci Resolve TCP Bridge Server

  Run inside Resolve's Fusion Console (Lua):
    dofile("/path/to/davinci-resolve-mcp/src/utils/resolve_bridge_server.lua")

  Exposes the Resolve scripting API over localhost TCP so that external
  Python processes can call it even when native IPC is blocked.

  Protocol: length-prefixed JSON (4-byte big-endian + JSON body)
  Default:  127.0.0.1:9876
]]

-- ---------------------------------------------------------------------------
-- LuaJIT FFI: POSIX sockets (macOS ARM64)
-- ---------------------------------------------------------------------------
local ffi = require("ffi")

ffi.cdef[[
  // Socket types & constants
  typedef int32_t  socklen_t;
  typedef uint8_t  sa_family_t;
  typedef uint16_t in_port_t;
  typedef uint32_t in_addr_t;

  struct in_addr  { in_addr_t s_addr; };
  struct sockaddr_in {
    uint8_t      sin_len;
    sa_family_t  sin_family;
    in_port_t    sin_port;
    struct in_addr sin_addr;
    char         sin_zero[8];
  };

  int    socket(int domain, int type, int protocol);
  int    bind(int sockfd, const void *addr, socklen_t addrlen);
  int    listen(int sockfd, int backlog);
  int    accept(int sockfd, void *addr, socklen_t *addrlen);
  int    close(int fd);
  int    setsockopt(int sockfd, int level, int optname,
                    const void *optval, socklen_t optlen);
  int    fcntl(int fd, int cmd, ...);

  ssize_t recv(int sockfd, void *buf, size_t len, int flags);
  ssize_t send(int sockfd, const void *buf, size_t len, int flags);

  uint16_t htons(uint16_t hostshort);
  uint32_t htonl(uint32_t hostlong);
  uint32_t ntohl(uint32_t netlong);

  char *strerror(int errnum);
  int  *__error(void);   // macOS errno location
]]

-- macOS constants
local AF_INET     = 2
local SOCK_STREAM = 1
local SOL_SOCKET  = 0xFFFF
local SO_REUSEADDR = 0x0004
local F_GETFL     = 3
local F_SETFL     = 4
local O_NONBLOCK  = 0x0004
local EAGAIN      = 35

local C = ffi.C

local function errno()
  return C.__error()[0]
end

local function strerror(e)
  return ffi.string(C.strerror(e))
end

-- ---------------------------------------------------------------------------
-- Minimal JSON encoder / decoder (pure Lua, no deps)
-- ---------------------------------------------------------------------------
local json = {}

-- Encode -------------------------------------------------------------------
local encode_value  -- forward declaration

local function encode_string(s)
  s = s:gsub('\\', '\\\\')
       :gsub('"', '\\"')
       :gsub('\n', '\\n')
       :gsub('\r', '\\r')
       :gsub('\t', '\\t')
  return '"' .. s .. '"'
end

local function encode_table(t)
  -- Detect array vs object: check for consecutive integer keys from 1
  local n = #t
  local is_array = true
  if n == 0 then
    -- Could be empty array or object – check for any key
    for _ in pairs(t) do
      is_array = false
      break
    end
    if is_array then return "[]" end
    -- else fall through to object encoding
  else
    for i = 1, n do
      if t[i] == nil then is_array = false; break end
    end
  end

  local parts = {}
  if is_array then
    for i = 1, n do
      parts[i] = encode_value(t[i])
    end
    return "[" .. table.concat(parts, ",") .. "]"
  else
    local i = 0
    for k, v in pairs(t) do
      i = i + 1
      parts[i] = encode_string(tostring(k)) .. ":" .. encode_value(v)
    end
    return "{" .. table.concat(parts, ",") .. "}"
  end
end

encode_value = function(v)
  local vtype = type(v)
  if v == nil then
    return "null"
  elseif vtype == "boolean" then
    return v and "true" or "false"
  elseif vtype == "number" then
    if v ~= v then return "null" end           -- NaN
    if v == math.huge then return "1e308" end
    if v == -math.huge then return "-1e308" end
    -- Use integer format when possible
    if v == math.floor(v) and math.abs(v) < 2^53 then
      return string.format("%.0f", v)
    end
    return tostring(v)
  elseif vtype == "string" then
    return encode_string(v)
  elseif vtype == "table" then
    return encode_table(v)
  else
    return "null"
  end
end

function json.encode(v)
  return encode_value(v)
end

-- Decode -------------------------------------------------------------------
local decode_value  -- forward declaration

local function skip_ws(s, pos)
  return s:match("^%s*()", pos)
end

local function decode_string(s, pos)
  -- pos should point at the opening quote
  assert(s:sub(pos, pos) == '"', "expected '\"'")
  local parts = {}
  local i = pos + 1
  while i <= #s do
    local c = s:sub(i, i)
    if c == '"' then
      return table.concat(parts), i + 1
    elseif c == '\\' then
      i = i + 1
      local esc = s:sub(i, i)
      if     esc == '"' then parts[#parts+1] = '"'
      elseif esc == '\\' then parts[#parts+1] = '\\'
      elseif esc == '/' then parts[#parts+1] = '/'
      elseif esc == 'n' then parts[#parts+1] = '\n'
      elseif esc == 'r' then parts[#parts+1] = '\r'
      elseif esc == 't' then parts[#parts+1] = '\t'
      elseif esc == 'u' then
        -- Simple unicode escape (BMP only, good enough)
        local hex = s:sub(i+1, i+4)
        local cp = tonumber(hex, 16)
        if cp and cp < 128 then
          parts[#parts+1] = string.char(cp)
        else
          parts[#parts+1] = "?"  -- non-ASCII placeholder
        end
        i = i + 4
      end
      i = i + 1
    else
      parts[#parts+1] = c
      i = i + 1
    end
  end
  error("unterminated string")
end

local function decode_number(s, pos)
  local num_str = s:match("^-?%d+%.?%d*[eE]?[+-]?%d*", pos)
  local val = tonumber(num_str)
  if not val then error("invalid number at " .. pos) end
  return val, pos + #num_str
end

local function decode_array(s, pos)
  local arr = {}
  pos = pos + 1  -- skip '['
  pos = skip_ws(s, pos)
  if s:sub(pos, pos) == ']' then return arr, pos + 1 end
  while true do
    local val
    val, pos = decode_value(s, pos)
    arr[#arr+1] = val
    pos = skip_ws(s, pos)
    local c = s:sub(pos, pos)
    if c == ']' then return arr, pos + 1 end
    if c == ',' then pos = skip_ws(s, pos + 1) end
  end
end

local function decode_object(s, pos)
  local obj = {}
  pos = pos + 1  -- skip '{'
  pos = skip_ws(s, pos)
  if s:sub(pos, pos) == '}' then return obj, pos + 1 end
  while true do
    local key, val
    key, pos = decode_string(s, pos)
    pos = skip_ws(s, pos)
    assert(s:sub(pos, pos) == ':', "expected ':'")
    pos = skip_ws(s, pos + 1)
    val, pos = decode_value(s, pos)
    obj[key] = val
    pos = skip_ws(s, pos)
    local c = s:sub(pos, pos)
    if c == '}' then return obj, pos + 1 end
    if c == ',' then pos = skip_ws(s, pos + 1) end
  end
end

decode_value = function(s, pos)
  pos = skip_ws(s, pos or 1)
  local c = s:sub(pos, pos)
  if c == '"' then return decode_string(s, pos)
  elseif c == '{' then return decode_object(s, pos)
  elseif c == '[' then return decode_array(s, pos)
  elseif c == 't' then
    assert(s:sub(pos, pos+3) == "true")
    return true, pos + 4
  elseif c == 'f' then
    assert(s:sub(pos, pos+4) == "false")
    return false, pos + 5
  elseif c == 'n' then
    assert(s:sub(pos, pos+3) == "null")
    return nil, pos + 4
  elseif c == '-' or (c >= '0' and c <= '9') then
    return decode_number(s, pos)
  else
    error("unexpected char '" .. c .. "' at position " .. pos)
  end
end

function json.decode(s)
  local val, _ = decode_value(s, 1)
  return val
end

-- ---------------------------------------------------------------------------
-- Object Registry
-- ---------------------------------------------------------------------------
local objects = {}
local next_id = 1

local function register_object(obj)
  local id = next_id
  objects[id] = obj
  next_id = next_id + 1
  return id
end

local function release_objects(ids)
  if not ids then return end
  for _, id in ipairs(ids) do
    if id ~= 1 then  -- never release the root resolve object
      objects[id] = nil
    end
  end
end

-- ---------------------------------------------------------------------------
-- Return value classification
-- ---------------------------------------------------------------------------
local function classify_value(val)
  if val == nil then
    return { type = "value", value = json.decode("null") }
  end

  local vtype = type(val)

  if vtype == "string" or vtype == "number" or vtype == "boolean" then
    return { type = "value", value = val }
  end

  if vtype == "userdata" then
    local id = register_object(val)
    return { type = "object", id = id }
  end

  if vtype == "table" then
    -- Check if it's an array
    local n = #val
    if n > 0 then
      local result = {}
      for i = 1, n do
        local item = val[i]
        if type(item) == "userdata" then
          local id = register_object(item)
          result[i] = { __resolve_obj__ = id }
        elseif type(item) == "table" then
          -- Recursively process nested tables
          result[i] = classify_table_contents(item)
        else
          result[i] = item
        end
      end
      return { type = "value", value = result }
    else
      -- Dict-like table
      local result = {}
      local has_keys = false
      for k, v in pairs(val) do
        has_keys = true
        if type(v) == "userdata" then
          local id = register_object(v)
          result[k] = { __resolve_obj__ = id }
        elseif type(v) == "table" then
          result[k] = classify_table_contents(v)
        else
          result[k] = v
        end
      end
      if not has_keys then
        return { type = "value", value = json.decode("null") }
      end
      return { type = "value", value = result }
    end
  end

  -- Fallback: unknown type, try tostring
  return { type = "value", value = tostring(val) }
end

-- Recursively process table contents, registering any userdata
function classify_table_contents(t)
  if type(t) ~= "table" then return t end
  local result = {}
  -- Handle array part
  local n = #t
  if n > 0 then
    for i = 1, n do
      local v = t[i]
      if type(v) == "userdata" then
        local id = register_object(v)
        result[i] = { __resolve_obj__ = id }
      elseif type(v) == "table" then
        result[i] = classify_table_contents(v)
      else
        result[i] = v
      end
    end
  else
    for k, v in pairs(t) do
      if type(v) == "userdata" then
        local id = register_object(v)
        result[k] = { __resolve_obj__ = id }
      elseif type(v) == "table" then
        result[k] = classify_table_contents(v)
      else
        result[k] = v
      end
    end
  end
  return result
end

-- ---------------------------------------------------------------------------
-- Request handling
-- ---------------------------------------------------------------------------
local function handle_request(req)
  -- Release stale objects first
  if req._release then
    release_objects(req._release)
  end

  local obj_id = req.obj_id
  local method = req.method
  local args   = req.args or {}

  -- Validate
  if not obj_id or not method then
    return { type = "error", message = "missing obj_id or method" }
  end

  local obj = objects[obj_id]
  if not obj then
    return { type = "error", message = "object " .. tostring(obj_id) .. " not found in registry" }
  end

  -- Resolve proxy object args (replace {__resolve_obj__: id} with actual objects)
  for i, arg in ipairs(args) do
    if type(arg) == "table" and arg.__resolve_obj__ then
      local ref = objects[arg.__resolve_obj__]
      if ref then
        args[i] = ref
      else
        return { type = "error", message = "arg references unknown object " .. tostring(arg.__resolve_obj__) }
      end
    end
  end

  -- Call the method
  local ok, result = pcall(function()
    return obj[method](obj, unpack(args))
  end)

  if not ok then
    return { type = "error", message = tostring(result) }
  end

  return classify_value(result)
end

-- ---------------------------------------------------------------------------
-- TCP Server
-- ---------------------------------------------------------------------------
local BIND_ADDR = "127.0.0.1"
local BIND_PORT = 9876

local function create_server()
  local fd = C.socket(AF_INET, SOCK_STREAM, 0)
  if fd < 0 then error("socket(): " .. strerror(errno())) end

  -- SO_REUSEADDR
  local optval = ffi.new("int[1]", 1)
  C.setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, optval, ffi.sizeof("int"))

  -- Bind
  local addr = ffi.new("struct sockaddr_in")
  addr.sin_family = AF_INET
  addr.sin_port = C.htons(BIND_PORT)
  -- 127.0.0.1 = 0x7F000001
  addr.sin_addr.s_addr = C.htonl(0x7F000001)

  if C.bind(fd, addr, ffi.sizeof(addr)) < 0 then
    C.close(fd)
    error("bind(): " .. strerror(errno()))
  end

  if C.listen(fd, 4) < 0 then
    C.close(fd)
    error("listen(): " .. strerror(errno()))
  end

  -- Non-blocking
  local flags = C.fcntl(fd, F_GETFL)
  C.fcntl(fd, F_SETFL, ffi.cast("int", bit.bor(flags, O_NONBLOCK)))

  return fd
end

-- ---------------------------------------------------------------------------
-- Client connection state
-- ---------------------------------------------------------------------------
local function new_client(fd)
  -- Set non-blocking
  local flags = C.fcntl(fd, F_GETFL)
  C.fcntl(fd, F_SETFL, ffi.cast("int", bit.bor(flags, O_NONBLOCK)))

  return {
    fd = fd,
    recv_buf = "",   -- accumulated receive data
  }
end

local function client_read(client)
  local buf = ffi.new("uint8_t[4096]")
  while true do
    local n = C.recv(client.fd, buf, 4096, 0)
    if n > 0 then
      client.recv_buf = client.recv_buf .. ffi.string(buf, n)
    elseif n == 0 then
      return false  -- client disconnected
    else
      local e = errno()
      if e == EAGAIN then
        break  -- no more data right now
      else
        return false  -- error
      end
    end
  end
  return true
end

local function client_extract_message(client)
  -- Need at least 4 bytes for the length prefix
  if #client.recv_buf < 4 then return nil end

  -- Read 4-byte big-endian length
  local b1, b2, b3, b4 = client.recv_buf:byte(1, 4)
  local msg_len = b1 * 16777216 + b2 * 65536 + b3 * 256 + b4

  -- Sanity check (max 16 MB)
  if msg_len > 16 * 1024 * 1024 then
    return nil, "message too large"
  end

  if #client.recv_buf < 4 + msg_len then return nil end

  local msg = client.recv_buf:sub(5, 4 + msg_len)
  client.recv_buf = client.recv_buf:sub(5 + msg_len)
  return msg
end

local function client_send(client, data)
  local len = #data
  -- 4-byte big-endian length prefix
  local header = string.char(
    bit.band(bit.rshift(len, 24), 0xFF),
    bit.band(bit.rshift(len, 16), 0xFF),
    bit.band(bit.rshift(len, 8), 0xFF),
    bit.band(len, 0xFF)
  )
  local payload = header .. data
  local sent = 0
  while sent < #payload do
    local n = C.send(client.fd, ffi.cast("const char *", payload) + sent,
                     #payload - sent, 0)
    if n > 0 then
      sent = sent + n
    elseif n < 0 then
      local e = errno()
      if e == EAGAIN then
        -- Briefly yield and retry
        if bmd and bmd.wait then bmd.wait(0.001) end
      else
        return false
      end
    end
  end
  return true
end

-- ---------------------------------------------------------------------------
-- Main server loop
-- ---------------------------------------------------------------------------
local function run_server()
  -- Register the root resolve object
  local resolve = fusion:GetResolve()
  if not resolve then
    print("[Bridge] ERROR: fusion:GetResolve() returned nil")
    print("[Bridge] Make sure you are running this from the Fusion Console")
    return
  end

  objects[1] = resolve
  next_id = 2

  local server_fd = create_server()
  print("[Bridge] Resolve Bridge Server listening on " .. BIND_ADDR .. ":" .. BIND_PORT)
  print("[Bridge] Root resolve object registered as ID 1")
  print("[Bridge] Press Ctrl+C in console or close Resolve to stop")

  local clients = {}
  local running = true

  while running do
    -- Accept new connections (non-blocking)
    local client_fd = C.accept(server_fd, nil, nil)
    if client_fd >= 0 then
      local client = new_client(client_fd)
      clients[client_fd] = client
      print("[Bridge] Client connected (fd=" .. client_fd .. ")")
    end

    -- Process each client
    local to_remove = {}
    for fd, client in pairs(clients) do
      local alive = client_read(client)
      if not alive then
        to_remove[#to_remove+1] = fd
      else
        -- Process all complete messages
        while true do
          local msg, err = client_extract_message(client)
          if err then
            print("[Bridge] Protocol error: " .. err)
            to_remove[#to_remove+1] = fd
            break
          end
          if not msg then break end

          -- Decode request
          local ok_decode, req = pcall(json.decode, msg)
          if not ok_decode then
            local resp = json.encode({ type = "error", message = "invalid JSON: " .. tostring(req) })
            if not client_send(client, resp) then
              to_remove[#to_remove+1] = fd
            end
          else
            -- Handle the request
            local ok_handle, resp = pcall(handle_request, req)
            local resp_json
            if ok_handle then
              resp_json = json.encode(resp)
            else
              resp_json = json.encode({ type = "error", message = tostring(resp) })
            end
            if not client_send(client, resp_json) then
              to_remove[#to_remove+1] = fd
            end
          end
        end
      end
    end

    -- Remove disconnected clients
    for _, fd in ipairs(to_remove) do
      print("[Bridge] Client disconnected (fd=" .. fd .. ")")
      C.close(fd)
      clients[fd] = nil
    end

    -- Yield to Resolve's event loop (keeps UI responsive)
    if bmd and bmd.wait then
      bmd.wait(0.05)
    end
  end

  -- Cleanup
  for fd, _ in pairs(clients) do
    C.close(fd)
  end
  C.close(server_fd)
  print("[Bridge] Server stopped")
end

-- ---------------------------------------------------------------------------
-- Start
-- ---------------------------------------------------------------------------
local ok, err = pcall(run_server)
if not ok then
  print("[Bridge] FATAL: " .. tostring(err))
end
