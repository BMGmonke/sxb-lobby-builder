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


# Give SXB-created PlayerInfo objects a complete, non-placeholder outfit.
replace_once(
    "src/Impostor.Api/Innersloth/Customization/PlayerOutfit.cs",
    "            internal set => SetField(ref _playerName, value);",
    "            set => SetField(ref _playerName, value);",
    "PlayerOutfit name setter")
replace_once(
    "src/Impostor.Api/Innersloth/Customization/PlayerOutfit.cs",
    "            internal set => SetField(ref _color, value);",
    "            set => SetField(ref _color, value);",
    "PlayerOutfit color setter")

replace_once(
    "src/Impostor.Server/Net/State/Game.Data.cs",
    """            playerInfo.ClientId = sender.Client.Id;
            playerInfo.FriendCode = sender.Client.FriendCode;""",
    """            playerInfo.ClientId = sender.Client.Id;
            playerInfo.CurrentOutfit.PlayerName = sender.Client.Name;
            playerInfo.CurrentOutfit.Color = Impostor.Api.Innersloth.Customization.ColorType.Cyan;
            playerInfo.FriendCode = sender.Client.FriendCode;""",
    "SXB PlayerInfo identity")

# The protocol-only host must publish the map and game-manager net objects;
# otherwise clients enter OnlineGame without a ship and remain in a void.
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/ShipStatus/InnerShipStatus.cs",
    """        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            throw new NotImplementedException();
        }""",
    """        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            return new ValueTask<bool>(false);
        }""",
    "ShipStatus spawn serializer")
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/GameManager/InnerGameManager.cs",
    """    public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
    {
        throw new System.NotImplementedException();
    }""",
    """    public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
    {
        return new ValueTask<bool>(false);
    }""",
    "GameManager spawn serializer")

p = Path("src/Impostor.Server/Net/State/Game.Data.cs")
s = p.read_text()
anchor = """                        sender.Scene = scene;

                        _logger.LogTrace("> Scene {0} to {1}", clientId, sender.Scene);

                        await SyncServerObjectsAsync(sender);"""
replacement = """                        sender.Scene = scene;

                        _logger.LogTrace("> Scene {0} to {1}", clientId, sender.Scene);

                        await EnsureSxbWorldObjectsAsync(sender);
                        await SyncServerObjectsAsync(sender);"""
if "EnsureSxbWorldObjectsAsync" not in s:
    if anchor not in s: raise SystemExit("SceneChange world-object insertion anchor missing")
    s = s.replace(anchor, replacement, 1)
    marker = """        private async ValueTask SyncServerObjectsAsync(ClientPlayer sender)
        {"""
    method = """        private async ValueTask EnsureSxbWorldObjectsAsync(ClientPlayer sender)
        {
            if (Host?.Client.Name != "BMGmonke?!" && sender.Client.Name is not ("SXBWatcher" or "BMGmonke?!"))
            {
                return;
            }

            if (!_allObjects.Values.OfType<InnerShipStatus>().Any())
            {
                var ship = (InnerShipStatus)ActivatorUtilities.CreateInstance(
                    _serviceProvider, typeof(InnerSkeldShipStatus), this);
                ship.SpawnFlags = SpawnFlags.None;
                ship.NetId = _nextNetId++;
                ship.OwnerId = ServerOwned;
                if (!AddNetObject(ship))
                {
                    throw new InvalidOperationException("Could not register the SXB Skeld ship object.");
                }
                await OnSpawnAsync(sender, ship);
                await SendObjectSpawnAsync(ship);
                _logger.LogInformation("Published Skeld ship object for SXB lobby {Code}.", Code);
            }

            if (!_allObjects.Values.OfType<InnerGameManager>().Any())
            {
                var manager = (InnerGameManager)ActivatorUtilities.CreateInstance(
                    _serviceProvider, typeof(InnerNormalGameManager), this);
                manager.SpawnFlags = SpawnFlags.None;
                manager.NetId = _nextNetId++;
                manager.OwnerId = ServerOwned;
                if (!AddNetObject(manager))
                {
                    throw new InvalidOperationException("Could not register the SXB normal game manager.");
                }
                await OnSpawnAsync(sender, manager);
                await SendObjectSpawnAsync(manager);
                _logger.LogInformation("Published normal game manager for SXB lobby {Code}.", Code);
            }
        }

"""
    if marker not in s: raise SystemExit("SyncServerObjects method insertion point missing")
    s = s.replace(marker, method + marker, 1)
    p.write_text(s)

print("SXB map/player initialization patch complete")

# Serialize the actual Skeld systems and normal-game options. Empty spawn
# payloads leave clients with a ShipStatus shell but no initialized systems.
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/ShipStatus/InnerShipStatus.cs",
    """        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            return new ValueTask<bool>(false);
        }""",
    """        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            foreach (var system in _systems)
            {
                writer.StartMessage((int)system.Key);
                system.Value.Serialize(writer, initialState);
                writer.EndMessage();
            }

            return new ValueTask<bool>(true);
        }""",
    "ShipStatus system-state serializer")

replace_once(
    "src/Impostor.Server/Net/Inner/Objects/GameManager/Logic/GameLogicComponent.cs",
    """    public virtual ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
    {
        throw new NotImplementedException();
    }""",
    """    public virtual ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
    {
        return ValueTask.FromResult(true);
    }""",
    "Game logic empty-state serializer")

replace_once(
    "src/Impostor.Server/Net/Inner/Objects/GameManager/InnerGameManager.cs",
    """    public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
    {
        return new ValueTask<bool>(false);
    }""",
    """    public override async ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
    {
        for (var i = 0; i < _logicComponents.Count; i++)
        {
            writer.StartMessage(i);
            await _logicComponents[i].SerializeAsync(writer, initialState);
            writer.EndMessage();
        }

        return true;
    }""",
    "GameManager logic-state serializer")

