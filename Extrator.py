
import os
import asyncio
import logging
import csv
import random
from telethon import TelegramClient,  utils, functions
from datetime import datetime
from telethon.tl import types as telethon_types

MAX_DAYS_ONLINE = 3
INCLUDE_RECENTLY = True 
OUTPUT='usuarios_backup.csv'
MAX_TASKS = 10
TIMOUT = 600
DELAY = 30

api_id = os.getenv('api_id')
api_hash = os.getenv('api_hash')
if not api_hash or not api_id:
    raise ValueError('Your Should config api_id and api_hash of Telegram in env')

if not os.path.exists('sessions'):
    os.makedirs('sessions')

def read_content(file):
    words = []
    if not os.path.exists(file):
        return words

    with open (file, 'r', encoding='utf-8', newline='') as f:
        for i, line in enumerate(f.readlines()):
            if i > 1 and line:
                words.append(line.strip())
        return words

admins_id = set()
usuarios = {}
grupos = []
processados = []
black_keys = read_content('blacklist.txt')
keys = read_content('keys.txt')

class CustomLogger(logging.Logger):
    def __init__(self, name, stdout=False, file='log.log', level=logging.INFO, detail=True):
        super().__init__(name, level)
        self.level=level
        self._setup_logger(stdout, file, detail)

    def _setup_logger(self, stdout, file, detail):
        self.setLevel(self.level)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s' if detail else '%(message)s')
        
        if stdout:
            stdout_handler = logging.StreamHandler()  
            stdout_handler.setLevel(self.level)  
            stdout_handler.setFormatter(formatter)
            self.addHandler(stdout_handler)

        file_handler = logging.FileHandler(file, encoding='utf-8', mode='w')
        file_handler.setLevel(self.level)
        file_handler.setFormatter(formatter)
        self.addHandler(file_handler)
        
    def print_output(self, *args, level=None, **kwargs):
        print(args[0])
        _level = getattr(logging, level.upper()) if level else self.level
        self._log(_level, args[0], args[1:], **kwargs)
        
logger = CustomLogger('Extrator', stdout=True)
now = datetime.now().timestamp()

async def sleep(seconds=DELAY):
    await asyncio.sleep(random.uniform(seconds/10,seconds))

    
def filtrar_user(participant) :
    try:
        status = participant.status
        if not participant.id:
            return False
    
        if not participant.username:
            return False
    
        if participant.bot:
            return False 
    
        if str(status).casefold().startswith("userstatusoffline"):
            try:
                was_online = status.was_online.timestamp()
                tdelta = abs(now - was_online) / (60 * 60 * 24)
                return tdelta <= MAX_DAYS_ONLINE
            except:
                return False

        elif status == telethon_types.UserStatusRecently():
            return INCLUDE_RECENTLY

        else:
            return False
    except:
        return False
        

def write_users(output=OUTPUT):
    rows = [[str(user.id), utils.get_display_name(user), user.username] for user in list(usuarios.values())]
    with open(output, 'w', encoding='utf-8', newline="") as f:
        csv_writer = csv.writer(f, delimiter=',')
        csv_writer.writerow(["ID", "Name", "Username", "Phone"])
        csv_writer.writerows(rows)
    
async def export_rapido(client, channel):
    if any (key in utils.get_display_name(channel) for key in black_keys):
        logging.info('Grupo na blacklist')
        return

    logger.info(f'Extraindo de {utils.get_display_name(channel)}')
    try:
        await sleep()
        async for participant in client.iter_participants(channel):
            if filtrar_user(participant):
                usuarios[participant.id] = participant
                
    except Exception as e:
        logger.warning(f' Erro no extrator {str(e)}')   
        
    await sleep()
    

async def process_entity(client: TelegramClient, chat):
    if chat.megagroup and chat.username:
        if chat.id not in processados:
            processados.append(chat.id)

            try:
                await asyncio.wait_for(export_rapido(client, chat), TIMOUT)
                write_users()
            except asyncio.TimeoutError:
                logger.info(f'Tiemout {chat.id} ')
            finally:
                    await sleep()

async def _seacher(client: TelegramClient, key):
    try:
        results = await client(functions.contacts.SearchRequest(
            q=key,
            limit=100
        ))
    except:
        await sleep()
    else:
        for chat in results.chats:
            await process_entity(client, chat)

    finally:
        await sleep()

async def seacher(client: TelegramClient):
    async for dialog in client.iter_dialogs():
        if dialog.is_channel:
            await process_entity(client, dialog.entity)
            
    for _ in range (3):
        if keys:
            key  = random.choice(keys)
            logger.info(f'Procurando grupos para: {key}')
            await _seacher(client, key)   

async def _run(session):
    client = TelegramClient(session, api_id, api_hash, base_logger=logger, receive_updates=False)
    await client.connect()
    me = await client.get_me()
    if me:
        try:
            await seacher(client)
        except Exception as e: 
            logger.warning(f'Erro ao procurar grupos: {e}')
    else:
        logger.warning(f'Session {session} nao logada ou banida')
        
    if client.is_connected():
        await client.disconnect()
        
async def run(session, semaphore):
    await asyncio.sleep(1)
    async with semaphore:
        try:
            await _run(f'sessions/{session}')
        except Exception as e:
            logger.warning(f'Erro ao processar session {session} {e}')

async def main():
    semaphore = asyncio.Semaphore(MAX_TASKS)
    tasks = []
    sessions = [
        session.replace('.session', '') 
        for session in os.listdir('sessions') 
        if session.endswith('.session')
    ]
    if not sessions:
        logger.print_output('Sem sessions na pasta')
    
    for phone in sessions:
        task = asyncio.create_task(run(phone, semaphore))
        tasks.append(task)

    await asyncio.gather(*tasks)
    logger.print_output(f'Salvando usuarios em usuarios_backup.csv')
    write_users()
    
        
if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        logger.print_output('\n Finalizado \n Coloque usuarios_backup.csv em Listas e use a opcao "backup" no Ninja')
        input('Aperte Enter para encerrar')
