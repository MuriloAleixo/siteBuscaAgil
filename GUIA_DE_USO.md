# Guia De Uso — BuscaÁgil

Este guia é sobre **usar** o BuscaÁgil depois que ele já está no ar. Se você
ainda precisa instalar/configurar o projeto, veja o [README.md](README.md).

## O Que É O BuscaÁgil

Um buscador pessoal de arquivos: você envia arquivos (ou cadastra links) e o
sistema guarda tudo no **seu próprio Google Drive**, numa pasta chamada
`buscaagil_upload`, e classifica cada item automaticamente (categoria, tags
e uma descrição curta) usando IA. Depois, você busca por nome, assunto ou
tipo de arquivo num só lugar — sem precisar vasculhar pastas do Drive na
mão.

Não existe usuário/senha própria do BuscaÁgil: o login é **só com conta
Google**.

## Login

Na página inicial, clique em **"Entrar com Google"** (no topo) ou em
**"Entrar com a conta Google"** (botão de destaque). Isso abre um modal —
clique em **"Continuar com Google"** pra ir pra tela de login/consentimento
do Google.

No mesmo consentimento, o Google já pede autorização pro BuscaÁgil acessar
uma pasta própria (`buscaagil_upload`) no seu Drive — não tem uma segunda
tela separada de "autorizar o Drive". Aceite as permissões pedidas
(identificação + acesso aos arquivos que o próprio BuscaÁgil cria) pra
continuar.

Depois do primeiro login, o sistema:
1. Cria a pasta `buscaagil_upload` no seu Drive (se ainda não existir).
2. Baixa o catálogo de arquivos de lá (se você já tiver usado o sistema antes).
3. Te leva pro painel principal.

Se esse passo falhar (token sem permissão de Drive, por exemplo), você cai
numa tela de erro com o botão **"Tentar de novo / reconceder acesso"** — ela
força o Google a pedir consentimento de novo. Se preferir logar com outra
conta Google, use **"Sair e usar outra conta"** na mesma tela.

## Painel Principal (Dashboard)

É a tela que abre depois do login — sua central de arquivos.

- **Busca**: a caixa principal no topo (`⌘ K` como atalho) já busca em todos
  os seus arquivos enquanto você digita. Essa busca é assistida por IA: além
  de bater com o nome do arquivo, ela interpreta o que você digitou e também
  considera categoria/tags/descrição geradas na classificação.
- **Filtrar por Formato** (barra lateral, ou os chips acima dos
  resultados): `Imagens`, `PDFs`, `Vídeos`, `Documentos`, `Planilhas`,
  `Links`, ou `Todos`.
- **Ordenar**: menu com `Mais recentes`, `Mais antigos`, `Nome (A–Z)`,
  `Maior tamanho`.
- **Modo Grade / Modo Lista**: alterna como os arquivos aparecem.
- Cada card mostra nome, tipo, tamanho e data — clique em qualquer um pra
  abrir os detalhes do arquivo.
- A barra lateral também mostra sua conta (nome, avatar) e o
  **espaço usado no Drive** (`X GB / Y GB`).

## Enviar Arquivos E Links

Clique em **"Enviar Arquivo"** (barra lateral) ou **"Enviar"** (cabeçalho)
pra abrir a tela de upload.

**Arquivos**: arraste e solte na área indicada, ou clique nela pra escolher
pelo seletor do sistema. Dá pra selecionar vários de uma vez. Arquivos
maiores que 100 MB são recusados automaticamente (aviso na tela).

**Links**: na caixa "Ou cadastre um link", cole uma URL (`https://...`) e
clique em **"Adicionar link"**. Útil pra guardar referências que não são
arquivo (uma página, uma planilha online etc.) no mesmo catálogo pesquisável.

Depois de enviar, cada item aparece na fila com um status (`Pendente`,
barra de progresso, `✓ Enviado` ou `Erro`). O envio em si é rápido; a
classificação e o envio definitivo pro Drive acontecem em segundo plano
logo em seguida — um aviso na tela confirma quando termina, já com a
categoria encontrada (ou avisando que não achou nenhuma, o que também é
normal). Se a classificação demorar mais que o normal (comum em vídeos, por
exemplo), pode fechar a tela de upload e continuar navegando — o aviso
aparece assim que terminar, em qualquer página do site que você estiver.
Clique em **"Ver Processamento"** pra acompanhar ao vivo, **"Ir para a
Busca"** quando terminar, ou
**"Enviar mais"** pra continuar enviando.

## Fila De Processamento

Tela dedicada (**"Fila de Processamento"** na barra lateral, ou o botão
**"Ver Processamento"** depois de um upload) pra acompanhar ao vivo tudo
que ainda está sendo classificado pela IA — sem precisar recarregar a
página. Cada item mostra um ícone girando com **"Classificando..."**
enquanto está em andamento; quando termina, mostra rapidamente o resultado
(a categoria encontrada, ou um aviso de erro) antes de sair da lista. Se
não houver nada em processamento, a tela mostra uma mensagem avisando que
está tudo em dia.

## Ver Detalhes De Um Arquivo

Clique em qualquer arquivo (no painel principal ou na busca) pra abrir a
página de detalhes. Nela você encontra:

- **Pré-visualização**: imagens aparecem direto na tela; vídeo, áudio,
  links e outros formatos mostram um atalho pra abrir no Google Drive (ou,
  no caso de link, um botão **"Acessar URL externa"**).
- **Descrição**: o resumo gerado automaticamente na classificação (quando
  existe).
- **Metadados**: nome, formato, tamanho, datas.
- **Classificação**: categoria e tags encontradas pela IA. Clique no ícone
  de lápis pra editar manualmente — útil quando o arquivo não foi
  classificado automaticamente (avisa isso na tela), ou quando você quer
  corrigir/completar categoria, tags (separadas por vírgula) e descrição.
  Clique em **"Salvar"** pra confirmar.
- **Ações**: **"Abrir no Google Drive"**, **"Baixar Arquivo"** (baixa o
  conteúdo real, não só o link), **"Copiar Link"** (copia o link desta
  página de detalhes), e **"Remover do Drive"**.

## Excluir Um Arquivo

Na página de detalhes do arquivo, clique em **"Remover do Drive"** e depois
confirme em **"Excluir"** no aviso que aparece. Isso remove o arquivo de
verdade do seu Google Drive e do catálogo do BuscaÁgil — **não tem como
desfazer** pelo próprio BuscaÁgil depois de confirmar (o Google Drive pode
ter sua própria lixeira, dependendo da conta).

## Buscar

Além da busca no painel principal, existe uma página de busca dedicada
(`Central de Pesquisa`) com o mesmo motor — filtros por tipo, ordenação e
resultados destacando o termo buscado. Ela não aparece no menu principal,
mas fica disponível navegando direto pra ela.

## Perfil

Clique no seu avatar (cabeçalho ou barra lateral) pra abrir o perfil: seus
dados de conta Google, um resumo de quantos arquivos você tem por tipo
(imagens, PDFs, vídeos), e o botão **"Desconectar"** pra sair da conta.

## Perguntas Frequentes

**Enviei um arquivo e ele não recebeu categoria/tags.** Normal em alguns
casos: o formato pode não ser suportado pela classificação automática, ou a
IA (local e/ou Gemini) pode estar indisponível no momento. O arquivo
continua salvo no seu Drive normalmente — você pode classificar
manualmente na página de detalhes.

**A busca não encontrou um arquivo que eu sei que enviei.** Tente buscar só
por parte do nome, ou pelo assunto/categoria em vez do nome exato — a busca
também considera o que a IA entendeu do conteúdo, não só o nome do arquivo.

**Onde meus arquivos ficam guardados de verdade?** No seu próprio Google
Drive, dentro de uma pasta chamada `buscaagil_upload`. O BuscaÁgil só
mantém um cache local temporário pra responder rápido — a fonte da verdade
é sempre o seu Drive.
