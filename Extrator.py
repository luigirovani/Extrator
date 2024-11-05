
import os
import asyncio
import logging
import csv
import random
import shutil 
import sys

from datetime import datetime
from telethon.errors import FloodWaitError
from telethon.tl import types as telethon_types
from utils.loggers.handles import get_colour_stdout_handler, get_file_handler
from utils.loggers.consts import normal
from utils.telegram import get_sessions
from dotenv import load_dotenv
load_dotenv()

from utils.loggers.colourprinter import ColourPrinter
from telethon import TelegramClient, utils, functions


MAX_DAYS_ONLINE = float(os.getenv('MAX_DAYS_ONLINE'))
INCLUDE_RECENTLY = os.getenv('INCLUDE_RECENTLY') == 'true' 
OUTPUT=os.getenv('OUTPUT')
MAX_TASKS = int(os.getenv('MAX_TASKS'))
DELAY = int(os.getenv('DELAY'))
FLOOD_SLEEP_THRESHOLD = int(os.getenv('FLOOD_SLEEP_THRESHOLD'))
NINJA_PATH= os.path.join(os.getenv('LOCALAPPDATA'), 'programs', 'Ninja Add')
TIMEOUT = int(os.getenv('TIMEOUT'))
PATTERN_KEYS = os.getenv('PATTERN_KEYS')
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
TOTAL_TIMEOUT = int(os.getenv('TOTAL_TIMEOUT'))
LIMIT_KEYS = int(os.getenv('LIMIT_KEYS'))
WAS_ONLINE_FACTOR = 60 * 60 * 24

class StdoutFilter:
    def __init__(self, original_stdout):
        self.original_stdout = original_stdout

    def write(self, message):
        if "Security error while unpacking a received message" not in message:
            self.original_stdout.write(message)

    def flush(self):
        self.original_stdout.flush()


sys.stdout = StdoutFilter(sys.stdout)
sys.stderr = StdoutFilter(sys.stderr)

class CustomLogger(logging.Logger):
    def __init__(self, name, stdout=False, file='log.log', level=logging.INFO, detail=True):
        super().__init__(name, level)
        self.level=level
        self._setup_logger(stdout, file, detail)
        self._printer = ColourPrinter()


    def _setup_logger(self, stdout, file, detail):
        self.setLevel(self.level)
        log_colors={
		    'DEBUG':    'light_purple',
		    'INFO':     'light_green',
		    'WARNING':  'light_yellow',
		    'ERROR':    'light_red',
		    'CRITICAL': 'red,bg_white'
	    }        
        if stdout:
            self.stdout_handler = get_colour_stdout_handler(
                fmt='%(log_color)s%(levelname)s: %(message)s',
                level=self.level,
                log_colors=log_colors
            )
            self.addHandler(self.stdout_handler)

        self.file_handler = get_file_handler(
            file=file,
            level=self.level,
            fmt=normal.LEVEL_TIME_MSG
        )
        self.addHandler(self.file_handler)
        
    def print_output(self, msg, colour='SANIC'):
        self._printer(msg=msg, colour=colour)
        
logger = CustomLogger('Extrator', stdout=True, level=logging.DEBUG)
now = datetime.now().timestamp()
os.makedirs('sessions', exist_ok=True)
mutex = asyncio.Lock()


def read_content(file):
    words = []
    if not os.path.exists(file):
        with open (file, 'w', encoding='utf-8') as f:
            if file == 'keys.txt' and PATTERN_KEYS:
                for k in PATTERN_KEYS.split(','):
                    f.write(k+'\n')

    with open (file, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f.readlines()):
            if i > 1 and line.strip():
                words.append(line.strip())
        return words

class User:
    def __init__(self, user_id: str, display_name: str, username: str):
        if not user_id.isdigit() or not display_name.strip() or not username.strip():
            raise ValueError("Missing value")
        
        self.id = int(user_id)
        self.display_name = display_name
        self.username = username

    def __repr__(self):
        return f"User(id={self.id}, display_name='{self.display_name}', username='{self.username}')"

def load_users(usuarios, file=OUTPUT):
    try:
        with open(file, 'r', encoding='utf-8', newline='') as f:
            csv_reader = csv.reader(f, delimiter=',')
            next(csv_reader)
            
            for row in csv_reader:
                try:
                    user = User(row[0].strip(), row[1], row[2])
                    usuarios[user.id] = user

                except Exception as e:
                    pass
                    #logger.debug(f'Erro ao processar usuário: {e}')

    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug(f'Erro ao carregar usuários de {file}: {e}')
    else:
        logger.debug(f'{len(usuarios)} Carregados na lista existente')

usuarios = {}
processados = []
black_keys = read_content('blacklist.txt')
whitelist_keys = read_content('whitelist.txt')
keys = read_content('keys.txt')


async def sleep(seconds=DELAY):
    await asyncio.sleep(random.uniform(seconds/10,seconds))

def get_display_name(entity):
    return entity.display_name if isinstance(entity, User) else utils.get_display_name(entity)
    
def filtrar_user(participant) :
    
    try:
        if not participant.username:
            return False
    
        elif participant.bot:
            return False

        status = participant.status
        
        if not status:
            return False

        elif isinstance(status, telethon_types.UserStatusOnline):
            return True

        elif isinstance(status, telethon_types.UserStatusRecently):
            return INCLUDE_RECENTLY

        elif isinstance(status, telethon_types.UserStatusOffline):
            was_online = status.was_online.timestamp()
            tdelta = abs(now - was_online) / (WAS_ONLINE_FACTOR)
            return tdelta <= MAX_DAYS_ONLINE

    except:
        return False
 

def write_users(output=OUTPUT):
    rows = [[str(user.id), get_display_name(user), user.username] for user in list(usuarios.values())]
    logger.print_output(f'DEBUG: {len(rows)} usuários na lista', 'BLUE')

    with open(output, 'w', encoding='utf-8', newline="") as f:
        csv_writer = csv.writer(f, delimiter=',')
        csv_writer.writerow(["ID", "Name", "Username", "Phone"])
        csv_writer.writerows(rows)

async def flush_users(output=OUTPUT):
    async with mutex:
        write_users(output)

async def insert_users(participants, output=OUTPUT):
    if len (participants) < 10:
        await sleep()
        return True

    async with mutex:
        for participant in participants:
            usuarios[participant.id] = participant
        write_users(output)

def check_channel(channel) -> bool:
    name = get_display_name(channel)
    username = channel.username if channel.username else ''

    if not channel.megagroup:
        return False

    if channel.id in processados:
        return False

    if whitelist_keys and not (any(key in name for key in whitelist_keys) or any(key in username for key in whitelist_keys) ):
        logger.debug(f'Grupo {name} não consta na whitelist')
        return False

    if black_keys and ( any(key in name for key in black_keys) or  any(key in username for key in black_keys)):
        logger.debug(f'Grupo {name} na blacklist')
        return False

    return True
    
async def export_rapido(client, channel):
    name = get_display_name(channel)
    logger.debug(f'Extraindo de {name}')
    await sleep()

    participants = [participant async for participant in client.iter_participants(channel) if filtrar_user(participant)] 
    result = await insert_users(participants)

    if result:
        logger.warning(f'Grupo {name} oculto')
    else:
        logger.info(f'Extração de {len(participants)} usuarios do grupo {name}')

async def process_entity(client: TelegramClient, channel):
    if not check_channel(channel):
        return None
    
    processados.append(channel.id)

    try:
        await asyncio.wait_for(export_rapido(client, channel), TIMEOUT)

    except asyncio.TimeoutError as e: 
        logger.error(f'Tiemout {channel} ')
        raise e
    except FloodWaitError as e:
        logger.error(f'Conta com flood por {e.seconds/60} minutos... abortando')
        raise e
    except (KeyboardInterrupt, asyncio.CancelledError, asyncio.TimeoutError) as e:
        logger.warning(f'Encerrando programa! Aguarde')
        raise KeyboardInterrupt()
    except Exception as e:
        logger.error(f'Erro ao extrair de {get_display_name(channel)} {e} ')
    finally:
        await sleep()

async def _seacher(client: TelegramClient, key):
    try:
        results = await client(functions.contacts.SearchRequest(
            q=key,
            limit=LIMIT_KEYS
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
    client = TelegramClient(session, API_ID, API_HASH, flood_sleep_threshold=FLOOD_SLEEP_THRESHOLD, receive_updates=False)
    await client.connect()
    await sleep(1)

    try:
        me = await client.get_me()
        if me:
            logger.print_output(f'Session {get_display_name(me)} Conectada', 'LC')
            try:
                await seacher(client)
            except KeyboardInterrupt as e:
                logger.debug(f'Encerrando programa! Aguarde...')
                raise e
            except Exception as e: 
                logger.warning(f'Erro ao procurar grupos: {e}')
        else:
            logger.warning(f'Session {session} deslogada ou banida')
        
    finally:
        if client.is_connected():
            await client.disconnect()
        
async def run(session, semaphore):
    async with semaphore:
        try:
            r = await _run(f'sessions/{session}')
        except KeyboardInterrupt as e:
            pass
        except Exception as e:
            logger.error(f'Erro ao processar session {session} {e}')
        finally:
            await sleep()

def save_users():
    logger.print_output(f'Salvando usuarios em usuarios_backup.csv')
    write_users()
    logger.debug(f'Total de {len(list(usuarios.values()))} usuários extraídos para a lista na lista')

    opt = input('Deseja exportar a lista direto para o ninja (s/n): ')
    if opt.lower() == 's':
        shutil.copy(OUTPUT, os.path.join(NINJA_PATH, 'Listas', 'usuarios_backup.csv'))
        logger.print_output('Lista exportada com sucesso \nLembre-se de ativar a opção "backup" no Ninja para usar a sua lista de membros')
    else:
        logger.print_output('Coloque usuarios_backup.csv em Listas e use a opcao "backup" no Ninja')

async def main():
    semaphore = asyncio.Semaphore(MAX_TASKS)
    tasks = []
    sessions = [s[0] for s in get_sessions('sessions', test_sql=True)]
    random.shuffle(sessions)

    if not sessions:
        logger.critical('Sem sessions na pasta')
        return False
    
    load_users(usuarios)
    write_users()
    logger.print_output(f'Iniciando extração de usuários das {len(sessions)} sessions disponíveis')

    for phone in sessions:
        await sleep(1.4)
        task = asyncio.create_task(run(phone, semaphore))
        tasks.append(task)

    try:
        await asyncio.wait_for(asyncio.gather(*tasks), TOTAL_TIMEOUT)
    except (asyncio.TimeoutError, KeyboardInterrupt, asyncio.CancelledError) as e:
        logger.debug('Encerrando programa! Aguarde...', 'LC')
        await asyncio.sleep(3)

    logger.print_output(f'Salvando usuarios em usuarios_backup.csv')
    save_users()

def test_session():
    session_path = os.path.join(NINJA_PATH, 'sessions')
    session_main_path = os.path.join(NINJA_PATH, 'session_main')

    logger.error('Sem sessions na pasta')
    logger.print_output('Deseja utilizar as sessions do Ninja?')
    logger.warning('Garanta que o Ninja Add não está em funcionamento para fazer esta importação')

    opt = input('s para Sim s N para não (s/n): ')
    if opt.lower() == 's':

        if not os.path.exists(session_path) or not os.path.exists(session_main_path):
            logger.critical('Ninja Add não encontrado')
            return False

        sessions = get_sessions(session_path, test_sql=True) + get_sessions(session_main_path, test_sql=True)
        for session in sessions:
            
            try:
                dest = os.path.join('sessions', session[0]+'.session')
                if not os.path.exists(dest):
                    shutil.copy(session[1], dest)
            except Exception as e:
                logger.warning(f'Erro ao copiar session {e}')

        logger.print_output('Sessions importadas com sucesso')
        return True

        
if __name__ == "__main__":
    logger.debug('Iniciando...')

    try:
        if get_sessions() or test_session():
            asyncio.run(main())
        else:
            logger.critical('Sem sessions')

    except KeyboardInterrupt as e:
        pass

    except Exception as e:
        logger.critical(f'Erro ao executar o script {e}')

    finally:
        logger.print_output('Finalizado\n\n')
        input('Pressione enter para encerrar')
