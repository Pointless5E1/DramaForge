/*
環境配置文件
開發環境
測試環境
線上環境
*/
//當前的環境
const env = 'local'

const EnvConfig = {
    local: {
        baseApi: 'http://localhost:54321',
    },
    prod: {
        baseApi: 'http://localhost:54321',

    },
}

export default {
    env,
    //mock的總開關
    ...EnvConfig[env]
}
