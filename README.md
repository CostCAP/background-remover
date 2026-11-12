# Background Remover 6.0

**Código:** MIT License. **Modelo:** BRIA RMBG-2.0 é descarregado separadamente e tem licença própria (CC BY-NC 4.0).

Ferramenta de linha de comandos para remover fundos de imagens em lote, mantendo a estrutura de diretórios da origem. Foi construída para fluxos de produção fotográfica em que processar imagens uma a uma seria demasiado repetitivo.

> **Licenciamento do modelo:** o programa utiliza os pesos briaai/RMBG-2.0. A página oficial indica atualmente CC BY-NC 4.0 para os pesos descarregados do Hugging Face; a utilização comercial desses pesos requer um acordo comercial com a BRIA. A licença do código deste projeto não altera a licença do modelo. Confirmar as condições diretamente na [model card oficial](https://huggingface.co/briaai/RMBG-2.0) antes de distribuir ou utilizar comercialmente.
>
> **Direitos sobre o código:** antes da publicação pública, confirmar por escrito que o código pode ser divulgado e que não contém propriedade, dados, caminhos ou procedimentos internos de uma entidade empregadora ou cliente.

## 1. Objetivo

O programa automatiza a remoção de fundo de coleções de imagens. Em vez de abrir cada ficheiro, executar a segmentação e guardar o resultado manualmente, o utilizador indica uma pasta base e o programa percorre os diretórios, processa os formatos suportados e escreve PNGs com transparência numa pasta de saída.

O objetivo é reduzir operações repetitivas e tornar o processamento de lotes previsível e retomável.

## 2. Funcionalidades implementadas

- **Segmentação com BRIA RMBG-2.0:** carrega o modelo através de Transformers e AutoModelForImageSegmentation.
- **GPU com fallback para CPU:** escolhe CUDA quando torch.cuda.is_available() devolve verdadeiro; caso contrário utiliza CPU.
- **Máscara alfa:** converte a saída do modelo numa máscara de 8 bits, recorta a zona de padding e redimensiona a máscara para a resolução original.
- **Preservação da imagem de origem:** os originais não são sobrescritos; os resultados são guardados como PNG.
- **Percurso recursivo:** pesquisa imagens dentro da pasta base e nas subpastas.
- **Estrutura de saída paralela:** replica os caminhos relativos dentro de Fundo Removido.
- **Retoma de trabalho:** procura resultados existentes com o prefixo sem_fundo_ e ignora ficheiros considerados já processados.
- **Reprocessamento forçado:** --force permite voltar a processar imagens que seriam ignoradas.
- **Pasta base configurável:** --base permite indicar uma localização diferente do diretório de execução.
- **Modelo configurável:** --hf-model permite indicar outro identificador de modelo compatível.
- **Credenciais Hugging Face:** aceita token por argumento, variável de ambiente ou keyring / Windows Credential Manager.
- **Compatibilidade com caminhos longos do Windows:** usa o prefixo de caminho estendido do Windows quando necessário.
- **Orientação EXIF:** aplica ImageOps.exif_transpose antes da segmentação.
- **HEIF/HEIC opcional:** tenta registar o descodificador pillow-heif; se não estiver instalado, o programa continua com os formatos suportados pelo Pillow.
- **Registo de erros:** acrescenta stack traces ao ficheiro errors.log para permitir diagnóstico posterior.

## 3. Formatos de imagem

| Formato | Extensões |
|---|---|
| PNG | .png |
| JPEG | .jpg, .jpeg, .jfif |
| Bitmap | .bmp |
| TIFF | .tiff |
| WebP | .webp |
| HEIF | .heic, .heif (depende de pillow-heif) |

A disponibilidade real de cada formato também depende dos descodificadores instalados no ambiente Python.

## 4. Arquitetura e fluxo de execução

1. **Argumentos CLI:** argparse lê a pasta base, o modelo, o token e as opções de reprocessamento.
2. **Credenciais:** get_huggingface_token() tenta, por esta ordem, argumento CLI, variáveis de ambiente, keyring e pedido de token oculto no terminal.
3. **Seleção do dispositivo:** o código escolhe CUDA se estiver disponível; caso contrário usa CPU.
4. **Carregamento:** AutoModelForImageSegmentation.from_pretrained() carrega o modelo com trust_remote_code=True e low_cpu_mem_usage=False; o modelo é movido para o dispositivo e colocado em modo de avaliação.
5. **Diagnóstico da pasta:** probe_path() confirma que a pasta base existe e pode ser listada.
6. **Inventário de resultados:** coletar_processados() recolhe nomes já presentes na pasta de saída.
7. **Recolha de imagens:** coletar_imagens_exceto_saida() percorre a pasta recursivamente e exclui diretórios com o nome de saída.
8. **Preparação da imagem:** remove_bg_rmbg2_from_pil() corrige EXIF, converte para RGB, redimensiona mantendo proporção e adiciona padding até 1024 × 1024.
9. **Inferência:** a imagem é convertida em tensor, normalizada com as médias e desvios utilizados no código e enviada ao modelo dentro de torch.no_grad().
10. **Reconstrução da máscara:** a predição final passa por sigmoid, é convertida para uma máscara de 8 bits, é retirada a região de padding e volta às dimensões originais.
11. **Aplicação do alfa:** a máscara é aplicada à imagem original convertida para RGBA.
12. **Exportação:** o resultado é guardado como sem_fundo_NOME-ORIGINAL.png dentro da subpasta equivalente em Fundo Removido.
13. **Resumo:** o terminal apresenta contagens de imagens processadas e falhadas; erros detalhados ficam em errors.log.

### Diagrama resumido

~~~text
Pasta base
   |
   v
Inventário recursivo de imagens
   |
   +----> Verificar resultados existentes
   |
   v
Corrigir orientação EXIF
   |
   v
RGB -> resize proporcional -> padding 1024x1024
   |
   v
PyTorch / BRIA RMBG-2.0
   |
   v
Predição -> sigmoid -> máscara alfa
   |
   v
Recortar padding -> redimensionar máscara
   |
   v
Aplicar transparência à imagem original
   |
   v
Fundo Removido / subpastas equivalentes / PNG
~~~

## 5. Requisitos

- Windows 10/11 ou ambiente Python compatível.
- Python 3.12, versão usada no ambiente de desenvolvimento.
- PyTorch e dependências compatíveis com a versão de Python e com o equipamento.
- Acesso ao modelo briaai/RMBG-2.0 no Hugging Face.
- Espaço em disco para os PNGs gerados e para os ficheiros do modelo.

### Dependências importadas pelo script

- Pillow
- numpy
- torch
- torchvision
- transformers

Dependências opcionais:

- pillow-heif — descodificação HEIF/HEIC.
- keyring — guardar e recuperar o token no gestor de credenciais do sistema.

A instalação exata do PyTorch deve seguir a configuração recomendada pelo próprio projeto PyTorch para o sistema e hardware utilizados. Não fixar uma combinação de CUDA/PyTorch sem validar primeiro os drivers e a GPU.

## 6. Preparação do ambiente

Criar um ambiente virtual para isolar as dependências:

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
~~~

Instalar a versão de PyTorch adequada ao equipamento e, depois, as bibliotecas adicionais:

~~~powershell
python -m pip install pillow numpy torchvision transformers
python -m pip install pillow-heif keyring
~~~

O comando acima é um ponto de partida, não uma matriz universal de versões. Validar compatibilidade de PyTorch, TorchVision, Python, drivers e GPU antes de publicar um ficheiro de dependências bloqueado.

## 7. Credenciais do Hugging Face

O script pode receber a credencial de três formas.

### Variável de ambiente

~~~powershell
$env:HF_TOKEN = "YOUR_HUGGING_FACE_READ_TOKEN"
python .\removerfundo6.0.py
~~~

Também reconhece HUGGINGFACE_TOKEN.

### Argumento

~~~powershell
python .\removerfundo6.0.py --hf-token YOUR_HUGGING_FACE_READ_TOKEN
~~~

Evitar este método em computadores partilhados: argumentos podem ficar visíveis no histórico do terminal ou na lista de processos.

### Windows Credential Manager

Instalar keyring e executar:

~~~powershell
python .\removerfundo6.0.py --save-hf-token
~~~

O script pede o token de forma oculta quando não encontra um valor disponível e tenta guardá-lo no serviço huggingface, utilizador token.

**Nunca publicar tokens, ficheiros .env, credenciais, logs com dados pessoais ou capturas de ecrã com segredos.** Um token que tenha sido incluído por engano num commit deve ser revogado no fornecedor.

## 8. Utilização

Executar na pasta do script:

~~~powershell
python .\removerfundo6.0.py
~~~

Indicar explicitamente a pasta de imagens:

~~~powershell
python .\removerfundo6.0.py --base "D:\Fotografias\Entrada"
~~~

Forçar o reprocessamento:

~~~powershell
python .\removerfundo6.0.py --base "D:\Fotografias\Entrada" --force
~~~

Escolher outro identificador de modelo:

~~~powershell
python .\removerfundo6.0.py --hf-model "briaai/RMBG-2.0"
~~~

### Resultado esperado

Se a origem tiver:

~~~text
Entrada/
  Equipa A/
    atleta_01.jpg
  Equipa B/
    atleta_02.png
~~~

A estrutura de saída será semelhante a:

~~~text
Diretório-de-execução/
  Fundo Removido/
    Equipa A/
      sem_fundo_atleta_01.png
    Equipa B/
      sem_fundo_atleta_02.png
~~~

A pasta Fundo Removido é criada relativamente ao diretório de execução atual (Path.cwd()), não necessariamente ao lado da pasta indicada em --base.

## 9. Decisões técnicas

### Padding quadrado

O modelo recebe 1024 × 1024. O script preserva a proporção da imagem e centraliza o conteúdo num canvas quadrado. Após a inferência, remove as margens artificiais antes de redimensionar a máscara. Assim, a geometria final volta a corresponder à imagem de origem.

### Máscara contínua

A predição passa por sigmoid e é convertida para 8 bits. O código não transforma a máscara num simples resultado preto/branco: mantém valores intermédios que representam transparência parcial nas margens do objeto.

### Processamento sem gradientes

A inferência decorre em torch.no_grad() e o modelo está em modo eval(), evitando cálculo de gradientes desnecessário.

### Retoma e nomes

A função de comparação normaliza o nome e remove sufixos finais do tipo _123. A verificação é baseada sobretudo no nome normalizado, não num hash do conteúdo.

## 10. Limitações conhecidas e pontos a melhorar

Esta secção é importante: a documentação não deve apresentar o programa como mais robusto do que o código atual demonstra.

1. **Colisões de nomes:** o conjunto de nomes processados é global para a pasta de saída. Duas subpastas com imagens diferentes mas com o mesmo nome-base podem levar a uma imagem ser ignorada incorretamente.
2. **Identificação por nome:** não existe checksum do ficheiro original; substituir uma imagem mantendo o mesmo nome pode não provocar reprocessamento automático.
3. **Contagem de progresso:** a versão atual é orientada a terminal e não apresenta uma barra gráfica.
4. **CPU:** funciona como alternativa, mas pode ser consideravelmente mais lenta do que GPU.
5. **Gestão de memória:** o modelo permanece carregado durante o processamento; não existe sistema de lotes de inferência ou limite de memória configurável.
6. **Erros de imagem:** os erros são registados, mas não existe ainda um relatório estruturado CSV/JSON por imagem.
7. **Token:** o argumento --hf-token pode ficar exposto no histórico; preferir variável de ambiente ou Credential Manager.
8. **trust_remote_code=True:** o carregamento permite código do repositório do modelo; rever a origem e versão do modelo antes de executar em ambientes sensíveis.
9. **Dependências opcionais:** HEIF/HEIC só funciona se o descodificador opcional estiver disponível.
10. **Licença do modelo:** os pesos RMBG-2.0 têm condições próprias; não assumir que o código Python pode ser usado comercialmente só por estar publicado sob uma licença permissiva.

## 11. Plano de validação antes de uma versão 1.0

- [ ] Testar PNG, JPG, JPEG, BMP, TIFF, WebP e HEIC (quando pillow-heif está instalado).
- [ ] Testar fotografia vertical, horizontal, quadrada e dimensões muito grandes.
- [ ] Confirmar orientação EXIF em fotografias de câmara/telemóvel.
- [ ] Confirmar que os originais nunca são alterados.
- [ ] Testar nomes repetidos em subpastas diferentes.
- [ ] Testar execução repetida sem --force.
- [ ] Testar --force.
- [ ] Testar caminho longo do Windows e caminhos com acentos.
- [ ] Testar GPU disponível e fallback CPU.
- [ ] Testar modelo sem autenticação, token inválido e acesso não autorizado.
- [ ] Confirmar que erros numa imagem não interrompem o resto do lote.
- [ ] Medir memória, duração e taxa de falha num conjunto de teste autorizado.
- [ ] Remover caminhos internos, imagens de clientes, credenciais e logs.
- [ ] Confirmar autorização do titular dos direitos e licença do modelo.

## 12. Privacidade e segurança

O processamento é local depois de descarregados os pesos, de acordo com o fluxo do script. O programa não implementa envio de imagens para um serviço remoto de processamento. O carregamento do modelo e a autenticação contactam o Hugging Face.

Para testes e demonstrações, usar imagens próprias ou com autorização. Não incluir fotografias de atletas, clientes ou colaboradores no repositório sem consentimento e base legal adequada.

## 13. Licenciamento

- **Código deste projeto:** MIT License; consultar o ficheiro LICENSE.
- **Modelo BRIA RMBG-2.0:** os pesos não são incluídos neste repositório. A model card oficial identifica CC BY-NC 4.0 para uso não comercial; a utilização comercial dos pesos self-hosted requer acordo separado com a BRIA.
- **Bibliotecas e dependências:** mantêm as respetivas licenças; consultar cada projeto original.

A licença MIT aplica-se apenas ao código original e à documentação deste repositório. Não concede direitos adicionais sobre os pesos BRIA, bibliotecas, fotografias, imagens de terceiros ou conteúdos processados.

Referências:
- [BRIA RMBG-2.0 — model card e licença](https://huggingface.co/briaai/RMBG-2.0)
- [MIT License](https://opensource.org/license/mit)
- [PyTorch — instalação](https://pytorch.org/get-started/locally/)
- [Hugging Face Transformers — documentação](https://huggingface.co/docs/transformers/index)

---

**Ficheiro principal:** removerfundo6.0.py
**Última modificação observada no ficheiro de origem:** 12-03-2026.
**Validação efetuada nesta publicação:** revisão estática de credenciais/caminhos e verificação de sintaxe Python. A inferência do modelo deve ser testada no ambiente e hardware de cada utilizador.