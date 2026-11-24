from pathlib import Path

def replace_once(path, old, new, label):
    p = Path(path)
    source = p.read_text()
    if new in source:
        print(f"{label}: already applied")
        return
    if old not in source:
        raise SystemExit(f"{label}: source anchor not found")
    p.write_text(source.replace(old, new, 1))
    print(f"{label}: applied")

# Keep SXB clients connected while their server-side PlayerControl is initialized.
p = Path("src/Impostor.Server/Net/State/ClientPlayer.cs")
s = p.read_text()
if "Retaining SXB bot" not in s:
    start = s.index("if (Character == null)", s.index("private async void RunSpawnTimeout"))
    brace = s.index("{", start)
    depth = 0
    end = None
    for i in range(brace, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise SystemExit("Unbalanced RunSpawnTimeout block")
    replacement = '''if (Character == null)
                  {
                      if (Client.Name is "SXBWatcher" or "BMGmonke?!")
                      {
                          _logger.LogInformation("{0} - Retaining SXB bot {1} ({2}) without Unity PlayerControl.", Game.Code, Client.Name, Client.Id);
                      }
                      else
                      {
                          _logger.LogInformation("{0} - Player {1} spawn timed out, kicking.", Game.Code, Client.Id);
                          await KickAsync();
                      }
                  }'''
    p.write_text(s[:start] + replacement + s[end:])

replace_once(
    "src/Impostor.Server/Net/Inner/Objects/InnerPlayerControl.cs",
    '''        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            throw new NotImplementedException();
        }''',
    '''        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            if (initialState) writer.Write(IsNew);
            writer.Write(PlayerId);
            return new ValueTask<bool>(true);
        }''',
    "PlayerControl serializer")

replace_once(
    "src/Impostor.Server/Net/Inner/Objects/InnerPlayerControl.cs",
    "        public byte PlayerId { get; private set; }",
    """        public byte PlayerId { get; private set; }

        internal void InitializeForServer(byte playerId)
        {
            IsNew = true;
            PlayerId = playerId;
        }""",
    "PlayerControl initializer")

p = Path("src/Impostor.Server/Net/Inner/Objects/Components/InnerPlayerPhysics.cs")
s = p.read_text()
old = '''        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            throw new NotImplementedException();
        }'''
new = '''        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            return new ValueTask<bool>(false);
        }'''
if new not in s:
    if old not in s: raise SystemExit("PlayerPhysics serializer anchor missing")
    s = s.replace(old, new, 1)
old = '''        public override ValueTask DeserializeAsync(IClientPlayer sender, IClientPlayer? target, IMessageReader reader, bool initialState)
        {
            throw new NotImplementedException();
        }'''
new = '''        public override ValueTask DeserializeAsync(IClientPlayer sender, IClientPlayer? target, IMessageReader reader, bool initialState)
        {
            return default;
        }'''
if new not in s:
    if old not in s: raise SystemExit("PlayerPhysics deserializer anchor missing")
    s = s.replace(old, new, 1)
p.write_text(s)

p = Path("src/Impostor.Server/Net/State/Game.Outgoing.cs")
s = p.read_text()
old = "                writer.WritePacked(obj.NetId);"
new = "                writer.WritePacked(component.NetId);"
if new not in s:
    if old not in s: raise SystemExit("Spawn component NetId anchor missing")
    p.write_text(s.replace(old, new, 1))

p = Path("src/Impostor.Server/Net/State/Game.Data.cs")
s = p.read_text()
old = """            await SendObjectSpawnAsync(playerInfo);
        }

        private async ValueTask DespawnPlayerInfoAsync"""
new = """            await SendObjectSpawnAsync(playerInfo);
            if (sender.Client.Name is "SXBWatcher" or "BMGmonke?!" || Host?.Client.Name == "BMGmonke?!")
            {
                await SpawnSxbPlayerControlAsync(sender, playerInfo);
            }
        }

        private async ValueTask SpawnSxbPlayerControlAsync(ClientPlayer sender, InnerPlayerInfo playerInfo)
        {
            var control = (InnerPlayerControl)ActivatorUtilities.CreateInstance(_serviceProvider, typeof(InnerPlayerControl), this);
            control.InitializeForServer(playerInfo.PlayerId);
            control.SpawnFlags = SpawnFlags.None;
            foreach (var component in control.GetComponentsInChildren<InnerNetObject>())
            {
                component.NetId = _nextNetId++;
                component.OwnerId = sender.Client.Id;
                if (!AddNetObject(component))
                {
                    throw new InvalidOperationException($"Could not register SXB player component {component.GetType().Name}.");
                }
                await OnSpawnAsync(sender, component);
            }
            await SendObjectSpawnAsync(control);
            _logger.LogInformation("Spawned server-side PlayerControl for {Name}, player ID {PlayerId}.", sender.Client.Name, playerInfo.PlayerId);
        }

        private async ValueTask DespawnPlayerInfoAsync"""
if "SpawnSxbPlayerControlAsync" not in s:
    if old not in s: raise SystemExit("PlayerInfo spawn insertion point missing")
    p.write_text(s.replace(old, new, 1))

print("SXB server spawn patch complete")
